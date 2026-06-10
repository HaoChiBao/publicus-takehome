"""Build search indexes: content chunks, embeddings, FTS text."""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from utils import PROCESSED_DIR, get_logger

log = get_logger("pipeline.index_search")

CHUNKS_PATH = PROCESSED_DIR / "grant_content_chunks.json"
EMBEDDINGS_PATH = PROCESSED_DIR / "grant_embeddings.json"
EMBED_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 600


def _chunk_text(text: str, chunk_type: str = "description") -> list[dict]:
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    for i in range(0, len(text), CHUNK_SIZE):
        part = text[i:i + CHUNK_SIZE].strip()
        if part:
            chunks.append({
                "chunk_index": len(chunks),
                "chunk_type": chunk_type,
                "content": part,
                "token_estimate": len(part.split()),
            })
    return chunks


def build_chunks(programs: list[dict]) -> list[dict]:
    """Split program text into RAG-ready chunks."""
    out = []
    for p in programs:
        pid = p["id"]
        texts = [
            ("description", p.get("description") or ""),
            ("eligibility", p.get("eligibility_narrative") or ""),
            ("summary", p.get("summary_1liner") or ""),
        ]
        for chunk_type, text in texts:
            for c in _chunk_text(text, chunk_type):
                out.append({"grant_program_id": pid, **c})
    log.info("Built %s content chunks", len(out))
    return out


def build_search_text(program: dict) -> str:
    """Concatenate fields used for FTS / embedding."""
    parts = [
        program.get("name"),
        program.get("department"),
        program.get("summary_1liner"),
        program.get("description"),
        program.get("eligibility_narrative"),
        program.get("target_audience"),
        " ".join(program.get("keywords") or []),
    ]
    return " ".join(p for p in parts if p)


def _embed_texts_openai(texts: list[str]) -> list[list[float]]:
    import os
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    # Batch up to 100
    all_embeddings: list[list[float]] = []
    batch_size = 50
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        all_embeddings.extend([d.embedding for d in resp.data])
    return all_embeddings


def build_embeddings(programs: list[dict], chunks: list[dict]) -> list[dict]:
    """Create program-level embeddings (optional — requires OPENAI_API_KEY)."""
    import os

    if not os.getenv("OPENAI_API_KEY"):
        log.info("No OPENAI_API_KEY — skipping embeddings (FTS + filters still work)")
        return []

    texts = []
    meta = []
    for p in programs:
        t = build_search_text(p)
        if t.strip():
            texts.append(t[:8000])
            meta.append({"entity_type": "program", "entity_id": p["id"], "content_text": t[:500]})

    for c in chunks[:200]:  # cap chunk embeddings for cost
        texts.append(c["content"][:2000])
        meta.append({
            "entity_type": "program_chunk",
            "entity_id": c["grant_program_id"],
            "content_text": c["content"][:300],
        })

    if not texts:
        return []

    log.info("Embedding %s texts with %s…", len(texts), EMBED_MODEL)
    vectors = _embed_texts_openai(texts)
    out = []
    for m, vec in zip(meta, vectors):
        out.append({**m, "model": EMBED_MODEL, "embedding": vec})
    log.info("Created %s embeddings", len(out))
    return out


def save_indexes(chunks: list[dict], embeddings: list[dict]) -> None:
    CHUNKS_PATH.write_text(json.dumps(chunks, indent=2, default=str), encoding="utf-8")
    EMBEDDINGS_PATH.write_text(json.dumps(embeddings, indent=2, default=str), encoding="utf-8")
    log.info("Wrote index snapshots: chunks, embeddings")


async def run(ctx) -> None:
    chunks = build_chunks(ctx.programs)
    embeddings = build_embeddings(ctx.programs, chunks)
    save_indexes(chunks, embeddings)
