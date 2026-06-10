// Tiny typed fetch wrapper around the FastAPI backend.
// Default "" uses Next.js rewrites (same-origin /api/* → backend) in local dev.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

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

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE ${path} -> ${res.status}`);
  return res.json();
}

// ---- Types ----
export interface MatchInfo {
  province: boolean;
  sector: boolean;
  size: boolean;
  naics?: boolean;
  activities?: boolean;
  hasHistory: boolean;
}
export interface ProgramStats {
  grant_program_id?: string;
  total_disbursed?: number;
  award_count?: number;
  recipient_count?: number;
  avg_award?: number;
  median_award?: number;
  p90_award?: number;
  largest_award?: number;
  provinces_active?: string[];
  sectors_active?: string[];
  naics_top_prefixes?: string[];
  yoy_growth_pct?: number;
  last_award_date?: string | null;
  award_by_fiscal_year?: { year: string; total: number }[];
  top_recipient_names?: string[];
}
export interface ProgramInsight {
  grant_program_id?: string;
  insight_type?: string;
  content: string;
  evidence?: Record<string, unknown>;
  model?: string;
}
export interface GrantCitation {
  program_id: string;
  name: string;
  stats?: ProgramStats | null;
  apply_url?: string | null;
}
export interface GrantAskResult {
  answer: string;
  programs: Program[];
  citations: GrantCitation[];
  insights: string[];
  total: number;
}
export interface Program {
  id: string;
  source?: string;
  name: string;
  department?: string;
  program_type?: string;
  description?: string;
  short_description?: string;
  long_description?: string;
  summary_1liner?: string;
  eligibility_narrative?: string;
  target_audience?: string;
  application_steps?: string[];
  stacking_notes?: string;
  keywords?: string[];
  min_amount?: number | null;
  max_amount?: number | null;
  eligible_provinces?: string[];
  eligible_sectors?: string[];
  eligible_sizes?: string[];
  eligible_activities?: string[];
  eligible_naics_prefixes?: string[];
  deadline?: string | null;
  is_open?: boolean;
  apply_url?: string | null;
  source_url?: string | null;
  last_updated?: string | null;
  sred_related?: boolean;
  tax_credit_type?: string | null;
  score?: number;
  match?: MatchInfo;
  match_reasons?: string[];
  stats?: ProgramStats;
}
export interface Award {
  id: string;
  recipient_id?: string;
  recipient_name?: string;
  recipient_name_raw?: string;
  program_id?: string | null;
  program_name_raw?: string;
  program_name_normalized?: string;
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
  ref_number?: string | null;
  amendment_number?: number;
  is_latest_amendment?: boolean;
  program_apply_url?: string | null;
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
export interface PeerCompany extends RecipientHit {
  similarity_score: number;
  match_reasons: string[];
  programs_in_common: string[];
  primary_sector?: string;
}
export interface Profile {
  session_id: string;
  name?: string;
  sector?: string;
  province?: string;
  size_band?: string;
  activities?: string[];
  naics_code?: string;
}
export interface DeadlineAlert {
  program_id: string;
  name: string;
  deadline: string;
  days_remaining: number;
  urgency: "critical" | "warning" | "info";
  apply_url?: string;
}
export interface ReadinessItem {
  key: string;
  label: string;
  status: "pass" | "fail" | "partial" | "unknown";
  required: boolean;
  detail?: string;
}
export interface ReadinessResult {
  readiness_score: number;
  items: ReadinessItem[];
  blockers: string[];
  next_steps: string[];
}
export interface OverlapFlag {
  type: string;
  severity: "warning" | "info";
  message: string;
  related_programs?: { id: string; name: string; program_type?: string }[];
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
      alerts: DeadlineAlert[];
      peers: PeerCompany[];
    }>(`/api/dashboard/${sessionId}`),

  exportDashboard: async (sessionId: string) => {
    const res = await fetch(`${API_URL}/api/dashboard/${sessionId}/export`);
    if (!res.ok) throw new Error("Export failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `publicus-grants-report-${sessionId.slice(0, 12)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  },

  searchPrograms: (params: {
    q?: string;
    sector?: string;
    province?: string;
    size_band?: string;
    program_type?: string;
    is_open?: boolean;
    activity?: string;
    min_amount?: number;
    max_amount?: number;
    session_id?: string;
    sort?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.sector) qs.set("sector", params.sector);
    if (params.province) qs.set("province", params.province);
    if (params.size_band) qs.set("size_band", params.size_band);
    if (params.program_type) qs.set("program_type", params.program_type);
    if (params.is_open !== undefined) qs.set("is_open", String(params.is_open));
    if (params.activity) qs.set("activity", params.activity);
    if (params.min_amount !== undefined) qs.set("min_amount", String(params.min_amount));
    if (params.max_amount !== undefined) qs.set("max_amount", String(params.max_amount));
    if (params.session_id) qs.set("session_id", params.session_id);
    if (params.sort) qs.set("sort", params.sort);
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    if (params.offset !== undefined) qs.set("offset", String(params.offset));
    const query = qs.toString();
    return get<{ programs: Program[]; total: number }>(
      `/api/programs${query ? `?${query}` : ""}`
    );
  },

  askGrants: (question: string, sessionId?: string) =>
    post<GrantAskResult>("/api/grants/ask", {
      question,
      session_id: sessionId,
    }),

  programAwards: (id: string, limit = 25, offset = 0) =>
    get<{ program: Program; awards: Award[]; total: number; insights?: ProgramInsight[] }>(
      `/api/awards/program/${id}?limit=${limit}&offset=${offset}`
    ),

  programInsights: (id: string) =>
    get<{ insights: ProgramInsight[] }>(`/api/programs/${id}/insights`),

  programReadiness: (programId: string, sessionId: string) =>
    get<ReadinessResult>(
      `/api/programs/${programId}/readiness?session_id=${sessionId}`
    ),

  programOverlap: (programId: string, sessionId: string) =>
    get<{ flags: OverlapFlag[] }>(
      `/api/programs/${programId}/overlap?session_id=${sessionId}`
    ),

  naicsLookup: (q: string) =>
    get<{ codes: { code: string; title: string; sector: string }[] }>(
      `/api/programs/naics/lookup?q=${encodeURIComponent(q)}`
    ),

  searchRecipients: (q: string, province?: string) =>
    get<{ recipients: RecipientHit[] }>(
      `/api/recipients/search?q=${encodeURIComponent(q)}${
        province ? `&province=${province}` : ""
      }`
    ),

  similarRecipients: (sessionId: string) =>
    get<{ peers: PeerCompany[] }>(
      `/api/recipients/similar?session_id=${sessionId}`
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

  getWatchlist: (sessionId: string) =>
    get<{ programs: Program[]; recipients: RecipientHit[] }>(
      `/api/watchlist/${sessionId}`
    ),

  addWatchlist: (sessionId: string, entityType: "program" | "recipient", entityId: string) =>
    post<{ ok: boolean }>(`/api/watchlist/${sessionId}`, {
      entity_type: entityType,
      entity_id: entityId,
    }),

  removeWatchlist: (sessionId: string, entityType: "program" | "recipient", entityId: string) =>
    del<{ ok: boolean }>(`/api/watchlist/${sessionId}/${entityType}/${entityId}`),

  pipelineStatus: () =>
    get<{ runs: any[] }>("/api/pipeline/status"),
};
