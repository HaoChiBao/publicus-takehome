"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ExternalLink,
  Lightbulb,
} from "lucide-react";
import {
  api,
  type Award,
  type OverlapFlag,
  type Program,
  type ProgramInsight,
  type ProgramStats,
  type ReadinessResult,
} from "@/lib/api";
import { amountRange, formatCurrency, formatCurrencyFull } from "@/lib/format";
import { sectorLabel } from "@/lib/constants";
import {
  normalizeProgram,
  readCachedProgram,
} from "@/lib/programCache";
import ReadinessChecklist from "@/components/ReadinessChecklist";
import RecipientTable from "@/components/RecipientTable";
import WatchlistButton from "@/components/WatchlistButton";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

export default function ProgramDetailPage() {
  const routeParams = useParams();
  const programId =
    typeof routeParams.id === "string"
      ? routeParams.id
      : Array.isArray(routeParams.id)
        ? routeParams.id[0]
        : "";

  const [program, setProgram] = useState<Program | null>(null);
  const [awards, setAwards] = useState<Award[]>([]);
  const [total, setTotal] = useState(0);
  const [insights, setInsights] = useState<ProgramInsight[]>([]);
  const [readiness, setReadiness] = useState<ReadinessResult | null>(null);
  const [overlapFlags, setOverlapFlags] = useState<OverlapFlag[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!programId) return;

    setLoading(true);
    setError(null);
    setReadiness(null);
    setOverlapFlags([]);

    const cached = readCachedProgram(programId);
    if (cached) {
      setProgram(normalizeProgram(cached));
    } else {
      setProgram(null);
    }
    setAwards([]);
    setTotal(0);
    setInsights([]);

    const session = localStorage.getItem("publicus_session");

    Promise.all([
      api.getProgram(programId).catch(() => null),
      api.programAwards(programId, 200).catch(() => null),
    ])
      .then(([programRes, awardsRes]) => {
        const resolved =
          programRes?.program ?? awardsRes?.program ?? cached ?? null;
        if (!resolved) {
          setError("Program not found.");
          return;
        }
        setProgram(normalizeProgram(resolved));
        if (awardsRes) {
          setAwards(awardsRes.awards);
          setTotal(awardsRes.total);
        }
        const insightList =
          programRes?.insights ?? awardsRes?.insights ?? [];
        if (insightList.length) setInsights(insightList);
      })
      .catch(() => {
        if (!cached) setError("Could not load this program. Try again.");
      })
      .finally(() => setLoading(false));

    if (session) {
      api.programReadiness(programId, session).then(setReadiness).catch(() => {});
      api
        .programOverlap(programId, session)
        .then((d) => setOverlapFlags(d.flags))
        .catch(() => {});
    }
  }, [programId]);

  const precomputed = program?.stats;

  const liveStats = useMemo(() => {
    const amounts = awards
      .map((a) => a.amount)
      .filter((x): x is number => x != null);
    const totalDisbursed = amounts.reduce((s, x) => s + x, 0);
    const recipients = new Set(
      awards.map((a) => a.recipient_id || a.recipient_name_raw)
    );
    const provinces = new Set(
      awards.map((a) => a.province).filter(Boolean) as string[]
    );
    const years = Array.from(
      new Set(awards.map((a) => a.fiscal_year).filter(Boolean) as string[])
    ).sort();
    const byYear = years.map((y) => ({
      year: y,
      total: awards
        .filter((a) => a.fiscal_year === y)
        .reduce((s, a) => s + (a.amount || 0), 0),
    }));
    return {
      totalDisbursed,
      recipientCount: recipients.size,
      provinceCount: provinces.size,
      avg: amounts.length ? totalDisbursed / amounts.length : 0,
      median: median(amounts),
      largest: amounts.length ? Math.max(...amounts) : 0,
      yearRange: years.length
        ? `${years[0]} – ${years[years.length - 1]}`
        : "—",
      byYear,
      awardCount: total || awards.length,
    };
  }, [awards, total]);

  const stats = useMemo(
    () => mergeStats(precomputed, liveStats),
    [precomputed, liveStats]
  );

  if (!programId || (error && !program))
    return (
      <p className="text-center text-sm font-medium text-destructive">
        {error || "Invalid program link."}
      </p>
    );

  if (loading && !program)
    return (
      <div className="space-y-6">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );

  if (!program)
    return (
      <p className="text-center text-sm font-medium text-destructive">
        Program not found.
      </p>
    );

  const maxYear = Math.max(...stats.byYear.map((y) => y.total), 1);
  const summary =
    program.summary_1liner || program.short_description || program.description;

  return (
    <div className="space-y-6">
      <Link
        href="/grants"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> Back to grant search
      </Link>

      <Card>
        <CardContent className="p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                {program.program_type && (
                  <Badge>{program.program_type}</Badge>
                )}
                {program.source && (
                  <Badge variant="outline" className="uppercase">
                    {program.source}
                  </Badge>
                )}
                <Badge
                  variant={program.is_open === false ? "muted" : "secondary"}
                >
                  {program.is_open === false ? "Closed" : "Open"}
                </Badge>
                {program.sred_related && (
                  <Badge variant="outline">SR&amp;ED related</Badge>
                )}
              </div>
              <h1 className="text-2xl font-bold tracking-tight">
                {program.name}
              </h1>
              <p className="text-sm text-muted-foreground">
                {program.department}
              </p>
              {summary && (
                <p className="max-w-3xl text-sm leading-relaxed">{summary}</p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <WatchlistButton entityType="program" entityId={programId} />
              {program.apply_url && (
                <a
                  href={program.apply_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={buttonVariants()}
                >
                  Apply <ExternalLink className="size-4" />
                </a>
              )}
              {program.source_url && (
                <a
                  href={program.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={buttonVariants({ variant: "outline" })}
                >
                  Source <ExternalLink className="size-4" />
                </a>
              )}
            </div>
          </div>

          {program.keywords && program.keywords.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {program.keywords.map((kw) => (
                <Badge key={kw} variant="secondary">
                  {kw}
                </Badge>
              ))}
            </div>
          )}

          <Separator className="my-6" />

          <div className="grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-4">
            <Fact
              label="Funding range"
              value={amountRange(program.min_amount, program.max_amount)}
            />
            <Fact label="Program type" value={program.program_type || "—"} />
            <Fact label="Deadline" value={program.deadline || "Rolling / N/A"} />
            <Fact label="Last updated" value={program.last_updated || "—"} />
          </div>

          {program.target_audience && (
            <>
              <Separator className="my-6" />
              <Fact label="Target audience" value={program.target_audience} />
            </>
          )}

          <Separator className="my-6" />

          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Eligibility
          </p>
          {program.eligibility_narrative && (
            <p className="mb-4 max-w-3xl text-sm leading-relaxed text-muted-foreground">
              {program.eligibility_narrative}
            </p>
          )}
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <Eligibility label="Provinces" values={program.eligible_provinces} />
            <Eligibility label="Company size" values={program.eligible_sizes} />
            <Eligibility label="Activities" values={program.eligible_activities} />
            <Eligibility
              label="Sectors"
              values={(program.eligible_sectors || []).map((s) =>
                sectorLabel(s)
              )}
            />
          </div>

          {program.application_steps && program.application_steps.length > 0 && (
            <>
              <Separator className="my-6" />
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                How to apply
              </p>
              <ol className="list-decimal space-y-2 pl-5 text-sm text-muted-foreground">
                {program.application_steps.map((step, i) => (
                  <li key={i} className="leading-relaxed">
                    {step}
                  </li>
                ))}
              </ol>
            </>
          )}

          {program.stacking_notes && (
            <>
              <Separator className="my-6" />
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Stacking &amp; combinations
              </p>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {program.stacking_notes}
              </p>
            </>
          )}

          {program.long_description &&
            program.long_description !== program.description && (
              <>
                <Separator className="my-6" />
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Full description
                </p>
                <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">
                  {program.long_description}
                </p>
              </>
            )}
        </CardContent>
      </Card>

      {insights.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Funding insights
          </h2>
          {insights.map((ins, i) => (
            <Card key={i}>
              <CardContent className="flex gap-3 p-4 text-sm">
                <Lightbulb className="size-5 shrink-0 text-amber-600" />
                <div>
                  {ins.insight_type && (
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      {ins.insight_type.replace(/_/g, " ")}
                    </p>
                  )}
                  <p className="mt-0.5 leading-relaxed">{ins.content}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {overlapFlags.length > 0 && (
        <div className="space-y-2">
          {overlapFlags.map((flag) => (
            <Card
              key={flag.type}
              className={
                flag.severity === "warning"
                  ? "border-amber-500/50 bg-amber-50/50 dark:bg-amber-950/20"
                  : ""
              }
            >
              <CardContent className="flex gap-3 p-4 text-sm">
                <AlertTriangle
                  className={
                    flag.severity === "warning"
                      ? "size-5 shrink-0 text-amber-600"
                      : "size-5 shrink-0 text-muted-foreground"
                  }
                />
                <div>
                  <p className="font-medium">
                    {flag.type === "sred_overlap"
                      ? "SR&ED overlap"
                      : flag.type === "sred_program"
                        ? "SR&ED program"
                        : "Tax credit note"}
                  </p>
                  <p className="mt-0.5 text-muted-foreground">{flag.message}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {readiness && <ReadinessChecklist data={readiness} />}

      <div>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Award history analytics
          {precomputed && (
            <span className="ml-2 font-normal normal-case text-muted-foreground">
              (indexed from full disclosure data)
            </span>
          )}
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <MetricCard
            label="Total disbursed"
            value={formatCurrency(stats.totalDisbursed)}
          />
          <MetricCard label="Awards" value={String(stats.awardCount)} />
          <MetricCard
            label="Recipients"
            value={String(stats.recipientCount)}
          />
          <MetricCard label="Average award" value={formatCurrency(stats.avg)} />
          <MetricCard
            label="Median award"
            value={formatCurrency(stats.median)}
          />
          <MetricCard
            label="Largest award"
            value={formatCurrency(stats.largest)}
          />
        </div>

        {(precomputed?.provinces_active?.length ||
          precomputed?.sectors_active?.length) && (
          <div className="mt-3 flex flex-wrap gap-2">
            {precomputed?.provinces_active?.map((p) => (
              <Badge key={p} variant="outline">
                {p}
              </Badge>
            ))}
            {precomputed?.sectors_active?.map((s) => (
              <Badge key={s} variant="secondary">
                {sectorLabel(s)}
              </Badge>
            ))}
            {precomputed?.yoy_growth_pct != null && (
              <Badge variant="outline" className="tabular-nums">
                YoY {precomputed.yoy_growth_pct > 0 ? "+" : ""}
                {precomputed.yoy_growth_pct}%
              </Badge>
            )}
          </div>
        )}

        {stats.byYear.length > 1 && (
          <Card className="mt-3">
            <CardContent className="p-5">
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Disbursement by fiscal year
              </p>
              <div className="space-y-2.5">
                {stats.byYear.map((y) => (
                  <div key={y.year}>
                    <div className="flex justify-between text-xs">
                      <span className="tabular-nums">{y.year}</span>
                      <span className="font-medium tabular-nums">
                        {formatCurrencyFull(y.total)}
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-muted">
                      <div
                        className="h-1.5 rounded-full bg-foreground"
                        style={{ width: `${(y.total / maxYear) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {precomputed?.top_recipient_names &&
          precomputed.top_recipient_names.length > 0 && (
            <Card className="mt-3">
              <CardContent className="p-5">
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Top recipients
                </p>
                <div className="flex flex-wrap gap-2">
                  {precomputed.top_recipient_names.map((name) => (
                    <Badge key={name} variant="outline">
                      {name}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
      </div>

      <div>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Recipients &amp; awards ({total})
        </h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Companies that have received this grant. Click a row for agreement
          details; click a recipient name to view their full history.
        </p>
        <RecipientTable awards={awards} showRecipient linkRecipients />
      </div>
    </div>
  );
}

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
}

function parseFiscalYears(
  raw: ProgramStats["award_by_fiscal_year"]
): { year: string; total: number }[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
}

function mergeStats(
  precomputed: ProgramStats | undefined,
  live: {
    totalDisbursed: number;
    recipientCount: number;
    avg: number;
    median: number;
    largest: number;
    byYear: { year: string; total: number }[];
    awardCount: number;
  }
) {
  const precomputedYears = parseFiscalYears(precomputed?.award_by_fiscal_year);
  if (precomputed?.award_count) {
    return {
      totalDisbursed: precomputed.total_disbursed ?? live.totalDisbursed,
      recipientCount: precomputed.recipient_count ?? live.recipientCount,
      avg: precomputed.avg_award ?? live.avg,
      median: precomputed.median_award ?? live.median,
      largest: precomputed.largest_award ?? live.largest,
      byYear: precomputedYears.length ? precomputedYears : live.byYear,
      awardCount: precomputed.award_count ?? live.awardCount,
    };
  }
  return { ...live, awardCount: live.awardCount };
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 font-medium">{value}</p>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <p className="mt-1 text-xl font-bold tabular-nums">{value}</p>
      </CardContent>
    </Card>
  );
}

function Eligibility({
  label,
  values,
}: {
  label: string;
  values?: string[];
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {values && values.length > 0 ? (
          values.map((v) => (
            <Badge key={v} variant="secondary">
              {v}
            </Badge>
          ))
        ) : (
          <span className="text-sm text-muted-foreground">—</span>
        )}
      </div>
    </div>
  );
}
