"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { api, type Program } from "@/lib/api";
import {
  ACTIVITIES,
  PROVINCES,
  PROGRAM_TYPES,
  SECTORS,
  SIZE_BANDS,
} from "@/lib/constants";
import GrantAskPanel from "@/components/GrantAskPanel";
import ProgramCard from "@/components/ProgramCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const PAGE_SIZE = 20;

type SearchMode = "browse" | "ask";

export default function GrantsBrowsePage() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [mode, setMode] = useState<SearchMode>("ask");

  const [q, setQ] = useState("");
  const [sector, setSector] = useState("");
  const [province, setProvince] = useState("");
  const [sizeBand, setSizeBand] = useState("");
  const [programType, setProgramType] = useState("");
  const [isOpen, setIsOpen] = useState("");
  const [activity, setActivity] = useState("");
  const [sort, setSort] = useState("score");
  const [page, setPage] = useState(1);

  const [programs, setPrograms] = useState<Program[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const session = localStorage.getItem("publicus_session");
    if (!session) {
      router.push("/");
      return;
    }
    setSessionId(session);
  }, [router]);

  const fetchPrograms = useCallback(() => {
    if (!sessionId || mode !== "browse") return;
    setLoading(true);
    const offset = (page - 1) * PAGE_SIZE;
    api
      .searchPrograms({
        q: q || undefined,
        sector: sector || undefined,
        province: province || undefined,
        size_band: sizeBand || undefined,
        program_type: programType || undefined,
        is_open: isOpen === "" ? undefined : isOpen === "true",
        activity: activity || undefined,
        session_id: sessionId,
        sort,
        limit: PAGE_SIZE,
        offset,
      })
      .then((res) => {
        setPrograms(res.programs);
        setTotal(res.total);
      })
      .catch(() => {
        setPrograms([]);
        setTotal(0);
      })
      .finally(() => setLoading(false));
  }, [
    sessionId,
    mode,
    q,
    sector,
    province,
    sizeBand,
    programType,
    isOpen,
    activity,
    sort,
    page,
  ]);

  useEffect(() => {
    if (mode !== "browse") return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(fetchPrograms, q ? 300 : 0);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [fetchPrograms, q, mode]);

  function resetFilters() {
    setQ("");
    setSector("");
    setProvince("");
    setSizeBand("");
    setProgramType("");
    setIsOpen("");
    setActivity("");
    setSort("score");
    setPage(1);
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  if (!sessionId) return null;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Grant Search</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Ask questions in plain language or browse the full catalog with
          filters. Results use indexed eligibility, keywords, and award
          disbursement data.
        </p>
      </div>

      <div className="mb-6 flex gap-2">
        <Button
          variant={mode === "ask" ? "default" : "outline"}
          size="sm"
          onClick={() => setMode("ask")}
        >
          Smart search
        </Button>
        <Button
          variant={mode === "browse" ? "default" : "outline"}
          size="sm"
          onClick={() => setMode("browse")}
        >
          Browse &amp; filter
        </Button>
      </div>

      {mode === "ask" ? (
        <GrantAskPanel sessionId={sessionId} />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
          <div className="space-y-4 lg:col-span-1">
            <div className="space-y-2">
              <Label htmlFor="grant-search">Keyword search</Label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="grant-search"
                  value={q}
                  onChange={(e) => {
                    setQ(e.target.value);
                    setPage(1);
                  }}
                  placeholder="Name, sector, eligibility…"
                  className="pl-9"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="filter-sector">Sector</Label>
              <Select
                id="filter-sector"
                value={sector}
                onChange={(e) => {
                  setSector(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">All sectors</option>
                {SECTORS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="filter-province">Province</Label>
              <Select
                id="filter-province"
                value={province}
                onChange={(e) => {
                  setProvince(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">All provinces</option>
                {PROVINCES.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="filter-size">Company size</Label>
              <Select
                id="filter-size"
                value={sizeBand}
                onChange={(e) => {
                  setSizeBand(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">Any size</option>
                {SIZE_BANDS.map((b) => (
                  <option key={b} value={b}>
                    {b} employees
                  </option>
                ))}
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="filter-type">Program type</Label>
              <Select
                id="filter-type"
                value={programType}
                onChange={(e) => {
                  setProgramType(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">All types</option>
                {PROGRAM_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="filter-status">Status</Label>
              <Select
                id="filter-status"
                value={isOpen}
                onChange={(e) => {
                  setIsOpen(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">Open & closed</option>
                <option value="true">Open only</option>
                <option value="false">Closed only</option>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="filter-activity">Activity</Label>
              <Select
                id="filter-activity"
                value={activity}
                onChange={(e) => {
                  setActivity(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">Any activity</option>
                {ACTIVITIES.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="filter-sort">Sort by</Label>
              <Select
                id="filter-sort"
                value={sort}
                onChange={(e) => {
                  setSort(e.target.value);
                  setPage(1);
                }}
              >
                <option value="score">Best match</option>
                <option value="name">Name (A–Z)</option>
                <option value="amount">Funding amount</option>
                <option value="disbursement">Total disbursed</option>
                <option value="deadline">Deadline</option>
              </Select>
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={resetFilters}
              className="w-full"
            >
              Clear filters
            </Button>
          </div>

          <div className="lg:col-span-3">
            <div className="mb-3 flex items-center justify-between text-sm text-muted-foreground">
              <span>
                {loading
                  ? "Loading…"
                  : `${total} program${total === 1 ? "" : "s"} found`}
              </span>
              {!loading && totalPages > 1 && (
                <span>
                  Page {page} of {totalPages}
                </span>
              )}
            </div>

            <div className="space-y-3">
              {loading &&
                [0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-36 w-full" />
                ))}
              {!loading && programs.length === 0 && (
                <p className="py-12 text-center text-sm text-muted-foreground">
                  No programs match your filters. Try broadening your search or
                  switch to smart search.
                </p>
              )}
              {!loading &&
                programs.map((p) => (
                  <ProgramCard key={p.id} program={p} />
                ))}
            </div>

            {!loading && totalPages > 1 && (
              <div className="mt-6 flex items-center justify-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ChevronLeft className="size-4" />
                  Previous
                </Button>
                <span className="px-2 text-sm tabular-nums text-muted-foreground">
                  {page} / {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
