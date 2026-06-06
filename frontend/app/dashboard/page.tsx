"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowUpRight, TrendingUp } from "lucide-react";
import {
  api,
  type Program,
  type SectorSummary,
  type TrendingProgram,
} from "@/lib/api";
import { amountRange, formatCurrencyFull } from "@/lib/format";
import { sectorLabel } from "@/lib/constants";
import MatchScore from "@/components/MatchScore";
import SectorIntelCard from "@/components/SectorIntelCard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface DashboardData {
  profile: {
    name?: string;
    sector?: string;
    province?: string;
    size_band?: string;
  };
  matches: Program[];
  sector_summary: SectorSummary;
  trending: TrendingProgram[];
}

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const session = localStorage.getItem("publicus_session");
    if (!session) {
      router.push("/");
      return;
    }
    api
      .dashboard(session)
      .then(setData)
      .catch(() => setError("Could not load your dashboard. Is the API running?"));
  }, [router]);

  if (error)
    return (
      <p className="text-center text-sm font-medium text-destructive">{error}</p>
    );

  if (!data)
    return (
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="space-y-3 lg:col-span-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
        <div className="space-y-6 lg:col-span-3">
          <Skeleton className="h-80 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </div>
    );

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">
          {data.profile.name ? `${data.profile.name} · ` : ""}Grants Dashboard
        </h1>
        <p className="text-sm text-muted-foreground">
          {sectorLabel(data.profile.sector)} · {data.profile.province} ·{" "}
          {data.profile.size_band} employees
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        {/* Left panel — matches */}
        <section className="lg:col-span-2">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Grants You Match
            </h2>
            <span className="text-xs text-muted-foreground">
              {data.matches.length} programs
            </span>
          </div>
          <div className="space-y-3">
            {data.matches.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No matching programs found for this profile.
              </p>
            )}
            {data.matches.map((p) => (
              <MatchCard key={p.id} program={p} />
            ))}
          </div>
        </section>

        {/* Right column */}
        <div className="space-y-6 lg:col-span-3">
          <SectorIntelCard summary={data.sector_summary} />

          <section>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              On Your Radar
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {data.trending.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No fast-growing programs detected for this segment.
                </p>
              )}
              {data.trending.map((t) => (
                <Link key={t.program_id} href={`/program/${t.program_id}`}>
                  <Card className="h-full transition-colors hover:border-foreground">
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="text-sm font-semibold leading-tight">
                          {t.name}
                        </h3>
                        <Badge className="shrink-0 gap-1">
                          <TrendingUp className="size-3" />
                          {t.yoy_change_pct}%
                        </Badge>
                      </div>
                      <p className="mt-2 text-xs text-muted-foreground">
                        {formatCurrencyFull(t.previous_total)} →{" "}
                        {formatCurrencyFull(t.latest_total)} in{" "}
                        {t.latest_fiscal_year}
                      </p>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function MatchCard({ program: p }: { program: Program }) {
  return (
    <Link href={`/program/${p.id}`} className="block">
      <Card className="transition-colors hover:border-foreground">
        <CardContent className="space-y-3 p-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="font-semibold leading-tight">{p.name}</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {p.department}
              </p>
            </div>
            <Badge className="shrink-0 tabular-nums">
              {Math.round((p.score || 0) * 100)}%
            </Badge>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 text-sm">
            <Badge variant="secondary">{amountRange(p.min_amount, p.max_amount)}</Badge>
            {p.program_type && (
              <Badge variant="outline">{p.program_type}</Badge>
            )}
          </div>

          {p.match && (
            <MatchScore
              province={p.match.province}
              sector={p.match.sector}
              size={p.match.size}
              hasHistory={p.match.hasHistory}
            />
          )}

          {p.match_reasons && p.match_reasons.length > 0 && (
            <ul className="space-y-0.5 border-t pt-2 text-xs text-muted-foreground">
              {p.match_reasons.map((r) => (
                <li key={r} className="flex items-start gap-1.5">
                  <ArrowUpRight className="mt-0.5 size-3 shrink-0" />
                  {r}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
