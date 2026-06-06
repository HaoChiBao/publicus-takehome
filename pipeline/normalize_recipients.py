"""Stage 4 — Recipient normalization (entity resolution).

Canonicalizes every company name in the award data into a single recipient
record. The flow is:

  1. Preprocess   — lowercase, strip punctuation + legal suffixes
  2. Block        — bucket by the first 3 chars so we only compare plausible pairs
  3. Fuzzy match  — rapidfuzz token_sort_ratio within each block
                       >= 88  -> definite duplicate (auto-merge)
                       75–87  -> ambiguous (ask the LLM)
                       < 75   -> different companies
  4. LLM confirm  — only the ambiguous 75–87 pairs, batched, to save cost
  5. Canonicalize — union matched pairs into clusters; pick the most common raw
                    name as the canonical, write recipients, link awards back

The matching logic is intentionally explicit and commented because it's the
part of the pipeline reviewers care about most.
"""
from __future__ import annotations

import asyncio
import re
from collections import Counter, defaultdict
from itertools import combinations

import pandas as pd
from rapidfuzz import fuzz

from llm import chat_json, llm_available
from utils import PROCESSED_DIR, get_logger, log_pipeline_run

log = get_logger("pipeline.normalize_recipients")

AUTO_MERGE = 88     # >= this -> same company
AMBIGUOUS_LOW = 75  # [75, 88) -> ask the LLM
LLM_BATCH = 20

# ---------------------------------------------------------------------------
# Step 1 — preprocessing
# ---------------------------------------------------------------------------
LEGAL_SUFFIXES = [
    r"\binc\.?\b", r"\bltd\.?\b", r"\blimited\b", r"\bcorp\.?\b",
    r"\bcorporation\b", r"\bltée?\b", r"\bs\.a\.r\.l\.?\b",
    r"\bllc\b", r"\bco\.?\b", r"\bcompany\b", r"\bgroupe?\b",
    r"\bgroup\b", r"\bsolutions?\b", r"\bservices?\b", r"\bconsulting\b",
]


def preprocess_name(name: str) -> str:
    name = (name or "").lower().strip()
    name = re.sub(r"[^\w\s]", " ", name)            # remove punctuation
    for suffix in LEGAL_SUFFIXES:
        name = re.sub(suffix, "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip()
    return name


# ---------------------------------------------------------------------------
# Union-Find for clustering matched pairs
# ---------------------------------------------------------------------------
class UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path compression
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb

    def clusters(self) -> dict:
        out = defaultdict(list)
        for x in self.parent:
            out[self.find(x)].append(x)
        return out


# ---------------------------------------------------------------------------
# Step 4 — LLM confirmation for ambiguous pairs
# ---------------------------------------------------------------------------
CONFIRM_PROMPT = (
    "Are these two entries the same Canadian company? Consider that company "
    "names may have slight variations, spelling differences, or abbreviations.\n\n"
    "Company A: {a}\nCompany B: {b}\n\n"
    'Reply with JSON: {{"same": true|false, "reason": "one sentence"}}'
)


async def _confirm_pair(a: str, b: str) -> bool:
    try:
        res = await chat_json([{"role": "user", "content": CONFIRM_PROMPT.format(a=a, b=b)}])
        return bool(res.get("same"))
    except Exception as e:  # noqa: BLE001
        log.warning("LLM confirm failed for (%r, %r): %s", a, b, e)
        return False


async def confirm_ambiguous(
    pairs: list[tuple[str, str, str, str]]
) -> list[tuple[str, str, bool]]:
    """pairs: (key_a, key_b, raw_a, raw_b). Returns (key_a, key_b, same).

    Offline (no LLM): fall back to a conservative rule — merge only when the
    looser token_set_ratio is also strong (>= 90), otherwise keep separate.
    """
    results = []
    if not llm_available():
        for ka, kb, ra, rb in pairs:
            same = fuzz.token_set_ratio(ka, kb) >= 90
            results.append((ka, kb, same))
        if pairs:
            log.info("Resolved %s ambiguous pairs via offline heuristic", len(pairs))
        return results

    for i in range(0, len(pairs), LLM_BATCH):
        batch = pairs[i:i + LLM_BATCH]
        verdicts = await asyncio.gather(*[_confirm_pair(ra, rb) for _, _, ra, rb in batch])
        for (ka, kb, _, _), same in zip(batch, verdicts):
            results.append((ka, kb, same))
    log.info("Resolved %s ambiguous pairs via LLM", len(pairs))
    return results


# ---------------------------------------------------------------------------
# Main resolution
# ---------------------------------------------------------------------------
async def resolve() -> pd.DataFrame:
    awards = pd.read_csv(PROCESSED_DIR / "awards_clean.csv")
    awards["recipient_name_raw"] = awards["recipient_name_raw"].fillna("").astype(str)

    # Distinct raw names + the attributes we'll roll up onto the canonical record.
    raw_names = sorted({n for n in awards["recipient_name_raw"] if n.strip()})
    key_for = {n: preprocess_name(n) for n in raw_names}

    # Step 2 — blocking by first 3 chars of the preprocessed key.
    blocks: dict[str, list[str]] = defaultdict(list)
    for raw, key in key_for.items():
        blocks[key[:3]].append(raw)
    log.info("Blocking: %s names -> %s blocks", len(raw_names), len(blocks))

    uf = UnionFind(raw_names)
    ambiguous: list[tuple[str, str, str, str]] = []
    auto = 0

    # Step 3 — compare only within blocks.
    for block_names in blocks.values():
        for a, b in combinations(block_names, 2):
            ka, kb = key_for[a], key_for[b]
            if not ka or not kb:
                continue
            score = fuzz.token_sort_ratio(ka, kb)
            if score >= AUTO_MERGE:
                uf.union(a, b)
                auto += 1
            elif score >= AMBIGUOUS_LOW:
                ambiguous.append((ka, kb, a, b))
    log.info("Fuzzy: %s auto-merges, %s ambiguous pairs", auto, len(ambiguous))

    # Step 4 — confirm the ambiguous band only.
    for ka, kb, same in await confirm_ambiguous(ambiguous):
        if same:
            # ka/kb are preprocessed keys; map back to a representative raw name.
            ra = next(n for n in raw_names if key_for[n] == ka)
            rb = next(n for n in raw_names if key_for[n] == kb)
            uf.union(ra, rb)

    # Step 5 — build canonical records.
    clusters = uf.clusters()
    log.info("Clustered %s raw names -> %s canonical recipients", len(raw_names), len(clusters))

    attrs = awards.set_index("recipient_name_raw")
    recipients = []
    canonical_of: dict[str, str] = {}   # raw name -> canonical name

    for members in clusters.values():
        # Most common raw spelling (by award frequency) becomes the canonical form.
        freq = awards[awards["recipient_name_raw"].isin(members)]["recipient_name_raw"]
        canonical = freq.value_counts().idxmax() if len(freq) else members[0]
        for m in members:
            canonical_of[m] = canonical

        sub = awards[awards["recipient_name_raw"].isin(members)]
        recipients.append({
            "name_normalized": canonical,
            "names_raw": sorted(set(members)),
            "business_number": _mode(sub.get("recipient_business_number")),
            "province": _mode(sub.get("province")),
            "city": _mode(sub.get("city")),
        })

    # Link every award to its canonical recipient name (load.py resolves to a UUID).
    awards["recipient_canonical"] = awards["recipient_name_raw"].map(canonical_of)
    awards.to_csv(PROCESSED_DIR / "awards_clean.csv", index=False)

    rec_df = pd.DataFrame(recipients)
    rec_df.to_csv(PROCESSED_DIR / "recipients.csv", index=False)
    log.info("Wrote %s recipients -> recipients.csv", len(rec_df))

    log_pipeline_run(
        "normalize_recipients", len(raw_names), len(rec_df),
        len(raw_names) - len(rec_df),
        {"auto_merges": auto, "ambiguous_pairs": len(ambiguous), "clusters": len(clusters)},
    )

    # Spot-check log: any cluster that merged >1 distinct spelling.
    for r in recipients:
        if len(r["names_raw"]) > 1:
            log.info("  cluster: %s  <-  %s", r["name_normalized"], r["names_raw"])
    return rec_df


def _mode(series) -> str | None:
    if series is None:
        return None
    s = series.dropna()
    s = s[s.astype(str).str.strip() != ""]
    if s.empty:
        return None
    return Counter(s.astype(str)).most_common(1)[0][0]


if __name__ == "__main__":
    asyncio.run(resolve())
