import type { Program } from "@/lib/api";

const STORAGE_KEY = "publicus_program_cache_v1";

export function cacheProgram(program: Program) {
  if (!program.id) return;
  try {
    const all = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "{}") as Record<
      string,
      Program
    >;
    all[program.id] = program;
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // sessionStorage may be unavailable
  }
}

export function cachePrograms(programs: Program[]) {
  for (const p of programs) cacheProgram(p);
}

export function readCachedProgram(id: string): Program | null {
  if (!id) return null;
  try {
    const all = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "{}") as Record<
      string,
      Program
    >;
    return all[id] ?? null;
  } catch {
    return null;
  }
}

/** Coerce API fields that may arrive as strings instead of arrays. */
export function normalizeProgram(program: Program): Program {
  const keywords = program.keywords;
  const steps = program.application_steps;
  return {
    ...program,
    keywords: Array.isArray(keywords)
      ? keywords
      : typeof keywords === "string"
        ? [keywords]
        : [],
    application_steps: Array.isArray(steps)
      ? steps
      : typeof steps === "string"
        ? [steps]
        : [],
  };
}
