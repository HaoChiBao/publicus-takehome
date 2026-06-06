// Tiny typed fetch wrapper around the FastAPI backend.
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} -> ${res.status}`);
  return res.json();
}

// ---- Types ----
export interface MatchInfo {
  province: boolean;
  sector: boolean;
  size: boolean;
  hasHistory: boolean;
}
export interface Program {
  id: string;
  source?: string;
  name: string;
  department?: string;
  program_type?: string;
  description?: string;
  min_amount?: number | null;
  max_amount?: number | null;
  eligible_provinces?: string[];
  eligible_sectors?: string[];
  eligible_sizes?: string[];
  eligible_activities?: string[];
  deadline?: string | null;
  is_open?: boolean;
  apply_url?: string | null;
  last_updated?: string | null;
  score?: number;
  match?: MatchInfo;
  match_reasons?: string[];
}
export interface Award {
  id: string;
  recipient_id?: string;
  recipient_name?: string;
  recipient_name_raw?: string;
  program_name_raw?: string;
  department?: string;
  agreement_type?: string;
  amount?: number | null;
  province?: string;
  city?: string;
  naics_code?: string;
  sector_normalized?: string;
  fiscal_year?: string;
  start_date?: string | null;
  end_date?: string | null;
  description?: string;
  source?: string;
}
export interface SectorSummary {
  sector: string;
  province?: string | null;
  total_amount: number;
  award_count: number;
  avg_amount: number;
  top_programs: { name: string; total: number; count: number }[];
  by_fiscal_year: { year: string; total: number }[];
  top_recipients: { name: string; total: number }[];
}
export interface TrendingProgram {
  name: string;
  program_id: string;
  latest_total: number;
  previous_total: number;
  yoy_change_pct: number;
  latest_fiscal_year: string;
}
export interface RecipientHit {
  id: string;
  name: string;
  province?: string;
  city?: string;
  award_count: number;
  total_amount: number;
}
export interface Profile {
  session_id: string;
  name?: string;
  sector?: string;
  province?: string;
  size_band?: string;
  activities?: string[];
}

// ---- Endpoints ----
export const api = {
  createProfile: (p: Omit<Profile, "session_id"> & { session_id?: string }) =>
    post<{ session_id: string; profile: Profile }>("/api/profile", p),

  dashboard: (sessionId: string) =>
    get<{
      profile: Profile;
      matches: Program[];
      sector_summary: SectorSummary;
      trending: TrendingProgram[];
    }>(`/api/dashboard/${sessionId}`),

  programAwards: (id: string, limit = 25, offset = 0) =>
    get<{ program: Program; awards: Award[]; total: number }>(
      `/api/awards/program/${id}?limit=${limit}&offset=${offset}`
    ),

  searchRecipients: (q: string, province?: string) =>
    get<{ recipients: RecipientHit[] }>(
      `/api/recipients/search?q=${encodeURIComponent(q)}${
        province ? `&province=${province}` : ""
      }`
    ),

  recipientAwards: (id: string) =>
    get<{
      recipient: RecipientHit & {
        name_normalized: string;
        total_received: number;
        award_count: number;
        provinces: string[];
      };
      awards: Award[];
      by_fiscal_year: { year: string; total: number; count: number }[];
    }>(`/api/recipients/${id}/awards`),

  pipelineStatus: () =>
    get<{ runs: any[] }>("/api/pipeline/status"),
};
