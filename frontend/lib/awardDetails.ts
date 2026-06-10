import type { Award } from "@/lib/api";

export interface AwardLink {
  label: string;
  href: string;
  external?: boolean;
}

export interface AwardField {
  label: string;
  value: string;
}

const SOURCE_LABELS: Record<string, string> = {
  open_canada: "Open Canada (Grants & Contributions)",
  nrc_irap: "NRC IRAP",
};

/** Proactive Disclosure — Grants and Contributions (Treasury Board consolidated dataset). */
const OPEN_CANADA_GRANTS_DATASET =
  "https://open.canada.ca/data/en/dataset/432527ab-7aac-45b5-81d6-7597107a7013";

/** Official grants search portal (replaces deprecated search.open.canada.ca/opendata). */
function openCanadaGrantsSearchUrl(query: string): string {
  return `https://search.open.canada.ca/grants/?search_text=${encodeURIComponent(query)}`;
}

function clean(value?: string | null): string | undefined {
  const s = (value ?? "").trim();
  return s || undefined;
}

/** Extra metadata fields beyond the table summary columns. */
export function awardExtraFields(award: Award): AwardField[] {
  const fields: AwardField[] = [];

  const ref = clean(award.ref_number);
  if (ref) fields.push({ label: "Reference number", value: ref });

  if (award.amendment_number != null && award.amendment_number > 0) {
    fields.push({
      label: "Amendment",
      value: String(award.amendment_number),
    });
  }

  const agreement = clean(award.agreement_type);
  if (agreement) fields.push({ label: "Agreement type", value: agreement });

  const sector = clean(award.sector_normalized);
  if (sector) fields.push({ label: "Sector", value: sector });

  const naics = clean(award.naics_code);
  if (naics) fields.push({ label: "NAICS code", value: naics });

  const city = clean(award.city);
  if (city) fields.push({ label: "City", value: city });

  const start = clean(award.start_date);
  if (start) fields.push({ label: "Start date", value: start });

  const end = clean(award.end_date);
  if (end) fields.push({ label: "End date", value: end });

  const source = award.source ? SOURCE_LABELS[award.source] ?? award.source : undefined;
  if (source) fields.push({ label: "Data source", value: source });

  return fields;
}

/** Internal routes and external source links when available. */
export function awardLinks(award: Award): AwardLink[] {
  const links: AwardLink[] = [];

  if (award.program_id) {
    links.push({
      label: "View program details",
      href: `/program/${award.program_id}`,
    });
    const applyUrl = clean(award.program_apply_url);
    if (applyUrl) {
      links.push({
        label: "Official program page",
        href: applyUrl,
        external: true,
      });
    }
  } else {
    const programQuery = clean(award.program_name_raw);
    if (programQuery) {
      links.push({
        label: "Search similar programs",
        href: `/grants?q=${encodeURIComponent(programQuery)}`,
      });
    }
  }

  const ref = clean(award.ref_number);
  if (award.source === "open_canada" && ref) {
    links.push({
      label: "Look up on Open Government",
      href: openCanadaGrantsSearchUrl(ref),
      external: true,
    });
    links.push({
      label: "Grants & contributions dataset",
      href: OPEN_CANADA_GRANTS_DATASET,
      external: true,
    });
  }

  if (award.source === "nrc_irap") {
    links.push({
      label: "About NRC IRAP",
      href: "https://nrc.canada.ca/en/support-technology-innovation/nrc-industrial-research-assistance-program-nrc-irap",
      external: true,
    });
  }

  return links;
}

export function awardDescription(award: Award): string | undefined {
  const desc = clean(award.description);
  const program = clean(award.program_name_raw);
  // Skip redundant one-line descriptions that repeat the program title.
  if (desc && program && desc.toLowerCase() === program.toLowerCase()) {
    return undefined;
  }
  return desc;
}

export function hasAwardExtraInfo(award: Award): boolean {
  return (
    awardExtraFields(award).length > 0 ||
    awardLinks(award).length > 0 ||
    !!awardDescription(award)
  );
}
