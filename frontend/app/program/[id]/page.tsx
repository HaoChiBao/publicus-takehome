"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowLeft, ExternalLink } from "lucide-react";
import {
  api,
  type Award,
  type OverlapFlag,
  type Program,
  type ReadinessResult,
} from "@/lib/api";
import { amountRange, formatCurrency, formatCurrencyFull } from "@/lib/format";
import { sectorLabel } from "@/lib/constants";
import ReadinessChecklist from "@/components/ReadinessChecklist";
import RecipientTable from "@/components/RecipientTable";
import WatchlistButton from "@/components/WatchlistButton";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

export default function ProgramDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const [program, setProgram] = useState<Program | null>(null);
  const [awards, setAwards] = useState<Award[]>([]);
  const [total, setTotal] = useState(0);
  const [readiness, setReadiness] = useState<ReadinessResult | null>(null);
  const [overlapFlags, setOverlapFlags] = useState<OverlapFlag[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const session = localStorage.getItem("publicus_session");
    api
      .programAwards(params.id, 200)
      .then((d) => {
        setProgram(d.program);
        setAwards(d.awards);
        setTotal(d.total);
      })
      .catch(() => setError("Program not found."));

    if (session) {
      api.programReadiness(params.id, session).then(setReadiness).catch(() => {});
      api.programOverlap(params.id, session).then((d) => setOverlapFlags(d.flags)).catch(() => {});
    }
  }, [params.id]);

  // Aggregate award analytics computed client-side from the award history.
  const stats = useMemo(() => {
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
      largest: amounts.length ? Math.max(...amounts) : 0,
      yearRange: years.length
        ? `${years[0]} – ${years[years.length - 1]}`
        : "—",
      byYear,
    };
  }, [awards]);

  if (error)
    return (
      <p className="text-center text-sm font-medium text-destructive">{error}</p>
    );

  if (!program)
    return (
      <div className="space-y-6">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );

  const maxYear = Math.max(...stats.byYear.map((y) => y.total), 1);

  return (
    <div className="space-y-6">
      <Link
        href="/dashboard"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> Back to dashboard
      </Link>

      {/* Header */}
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
              </div>
              <h1 className="text-2xl font-bold tracking-tight">
                {program.name}
              </h1>
              <p className="text-sm text-muted-foreground">
                {program.department}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <WatchlistButton entityType="program" entityId={params.id} />
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
            </div>
          </div>

          {program.description && (
            <p className="mt-4 max-w-3xl text-sm leading-relaxed text-muted-foreground">
              {program.description}
            </p>
          )}

          <Separator className="my-6" />

          {/* Funding + key facts */}
          <div className="grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-4">
            <Fact label="Funding range" value={amountRange(program.min_amount, program.max_amount)} />
            <Fact label="Program type" value={program.program_type || "—"} />
            <Fact label="Deadline" value={program.deadline || "Rolling / N/A"} />
            <Fact label="Last updated" value={program.last_updated || "—"} />
          </div>

          <Separator className="my-6" />

          {/* Eligibility */}
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Eligibility
          </p>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <Eligibility
              label="Provinces"
              values={program.eligible_provinces}
            />
            <Eligibility
              label="Company size"
              values={program.eligible_sizes}
            />
            <Eligibility
              label="Activities"
              values={program.eligible_activities}
            />
            <Eligibility
              label="Sectors"
              values={(program.eligible_sectors || []).map((s) =>
                sectorLabel(s)
              )}
            />
          </div>
        </CardContent>
      </Card>

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

      {/* Award analytics derived from history */}
      <div>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Award history analytics
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <MetricCard label="Total disbursed" value={formatCurrency(stats.totalDisbursed)} />
          <MetricCard label="Awards" value={String(total || awards.length)} />
          <MetricCard label="Recipients" value={String(stats.recipientCount)} />
          <MetricCard label="Average award" value={formatCurrency(stats.avg)} />
          <MetricCard label="Largest award" value={formatCurrency(stats.largest)} />
          <MetricCard label="Years covered" value={stats.yearRange} />
        </div>

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
      </div>

      {/* Full award history table */}
      <div>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Recipients &amp; awards ({total})
        </h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Every company that has received this grant. Click a row for the full
          agreement detail.
        </p>
        <RecipientTable awards={awards} showRecipient />
      </div>
    </div>
  );
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
