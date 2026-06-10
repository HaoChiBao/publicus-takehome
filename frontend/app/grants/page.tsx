"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
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
import { amountRange } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const PAGE_SIZE = 20;

export default function GrantsBrowsePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [sessionId, setSessionId] = useState<string | null>(null);

  const [q, setQ] = useState(() => searchParams.get("q") ?? "");
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
    if (!sessionId) return;
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
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(fetchPrograms, q ? 300 : 0);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [fetchPrograms, q]);

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

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Grant Programs</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Browse all available federal programs. Filter by eligibility, type, and
          funding — match scores reflect your company profile.
        </p>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-4">
        <div className="space-y-4 lg:col-span-1">
          <div className="space-y-2">
            <Label htmlFor="grant-search">Search</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="grant-search"
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPage(1);
                }}
                placeholder="Program name…"
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
              <option value="deadline">Deadline</option>
            </Select>
          </div>

          <Button variant="outline" size="sm" onClick={resetFilters} className="w-full">
            Clear filters
          </Button>
        </div>

        <div className="lg:col-span-3">
          <div className="mb-3 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {loading ? "Loading…" : `${total} program${total === 1 ? "" : "s"} found`}
            </span>
            {!loading && totalPages > 1 && (
              <span>
                Page {page} of {totalPages}
              </span>
            )}
          </div>

          <div className="space-y-3">
            {loading &&
              [0, 1, 2].map((i) => <Skeleton key={i} className="h-28 w-full" />)}
            {!loading && programs.length === 0 && (
              <p className="py-12 text-center text-sm text-muted-foreground">
                No programs match your filters. Try broadening your search.
              </p>
            )}
            {!loading &&
              programs.map((p) => (
                <Link key={p.id} href={`/program/${p.id}`} className="block">
                  <Card className="transition-colors hover:border-foreground">
                    <CardContent className="space-y-2 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h3 className="font-semibold leading-tight">{p.name}</h3>
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            {p.department}
                          </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          {p.score !== undefined && (
                            <Badge className="tabular-nums">
                              {Math.round(p.score * 100)}% match
                            </Badge>
                          )}
                          {p.is_open === false && (
                            <Badge variant="outline">Closed</Badge>
                          )}
                        </div>
                      </div>
                      {p.description && (
                        <p className="line-clamp-2 text-sm text-muted-foreground">
                          {p.description}
                        </p>
                      )}
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant="secondary">
                          {amountRange(p.min_amount, p.max_amount)}
                        </Badge>
                        {p.program_type && (
                          <Badge variant="outline">{p.program_type}</Badge>
                        )}
                        {p.deadline && (
                          <Badge variant="outline" className="tabular-nums">
                            Due {p.deadline}
                          </Badge>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </Link>
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
    </div>
  );
}
