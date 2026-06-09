export const SECTORS: { value: string; label: string }[] = [
  { value: "IT_SOFTWARE", label: "IT / Software" },
  { value: "ENGINEERING", label: "Engineering" },
  { value: "CYBERSECURITY", label: "Cybersecurity" },
  { value: "MANAGEMENT_CONSULTING", label: "Management Consulting" },
  { value: "LIFE_SCIENCES", label: "Life Sciences" },
  { value: "CLEAN_TECH", label: "Clean Tech" },
  { value: "OTHER", label: "Other" },
];

export const PROVINCES: { value: string; label: string }[] = [
  { value: "ON", label: "Ontario" },
  { value: "QC", label: "Quebec" },
  { value: "BC", label: "British Columbia" },
  { value: "AB", label: "Alberta" },
  { value: "MB", label: "Manitoba" },
  { value: "SK", label: "Saskatchewan" },
  { value: "NS", label: "Nova Scotia" },
  { value: "NB", label: "New Brunswick" },
  { value: "NL", label: "Newfoundland and Labrador" },
  { value: "PE", label: "Prince Edward Island" },
  { value: "NT", label: "Northwest Territories" },
  { value: "NU", label: "Nunavut" },
  { value: "YT", label: "Yukon" },
];

export const SIZE_BANDS = ["1-10", "11-50", "51-200", "200+"];

export const ACTIVITIES = [
  "R&D",
  "Export",
  "Hiring",
  "Digital Transformation",
  "Equipment",
  "Clean Tech",
];

export const PROGRAM_TYPES = [
  "Grant",
  "Loan",
  "Tax Credit",
  "Advisory",
  "Other",
];

export const COMMON_NAICS: { code: string; title: string; sector: string }[] = [
  { code: "541510", title: "Computer Systems Design", sector: "IT_SOFTWARE" },
  { code: "541512", title: "Computer Systems Design Services", sector: "CYBERSECURITY" },
  { code: "541330", title: "Engineering Services", sector: "ENGINEERING" },
  { code: "541611", title: "Management Consulting", sector: "MANAGEMENT_CONSULTING" },
  { code: "541714", title: "R&D in Biotechnology", sector: "LIFE_SCIENCES" },
  { code: "541620", title: "Environmental Consulting", sector: "CLEAN_TECH" },
];

export function sectorLabel(value?: string): string {
  return SECTORS.find((s) => s.value === value)?.label || value || "—";
}
