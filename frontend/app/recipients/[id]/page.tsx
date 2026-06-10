"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { api, type Award } from "@/lib/api";
import { formatCurrency, formatCurrencyFull } from "@/lib/format";
import { sectorLabel } from "@/lib/constants";
import RecipientTable from "@/components/RecipientTable";
import WatchlistButton from "@/components/WatchlistButton";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

interface RecipientDetail {
  name_normalized: string;
  total_received: number;
  award_count: number;
  provinces: string[];
}

export default function RecipientHistoryPage({
  params,
}: {
  params: { id: string };
}) {
  const [recipient, setRecipient] = useState<RecipientDetail | null>(null);
  const [awards, setAwards] = useState<Award[]>([]);
  const [byYear, setByYear] = useState<
    { year: string; total: number; count: number }[]
  >([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .recipientAwards(params.id)
      .then((d) => {
        if (!d.recipient) {
          setError("Recipient not found.");
          return;
        }
        setRecipient(d.recipient as unknown as RecipientDetail);
        setAwards(d.awards);
        setByYear(d.by_fiscal_year);
      })
      .catch((err: Error) => {
        setError(
          err.message.includes("404")
            ? "Recipient not found."
            : "Could not load recipient. Try again."
        );
      });
  }, [params.id]);

  const topSectors = useMemo(() => {
    const totals: Record<string, number> = {};
    for (const a of awards) {
      const s = a.sector_normalized;
      if (s) totals[s] = (totals[s] || 0) + (a.amount || 0);
    }
    return Object.entries(totals)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4);
  }, [awards]);

  const largest = useMemo(
    () =>
      awards.reduce((m, a) => Math.max(m, a.amount || 0), 0),
    [awards]
  );

  if (error)
    return (
      <p className="text-center text-sm font-medium text-destructive">{error}</p>
    );

  if (!recipient)
    return (
      <div className="space-y-6">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );

  const maxYear = Math.max(...byYear.map((y) => y.total), 1);

  return (
    <div className="space-y-6">
      <Link
        href="/recipients"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> Back to search
      </Link>

      <Card>
        <CardContent className="p-6">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Full grant history for
          </p>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <h1 className="text-2xl font-bold tracking-tight">
              {recipient.name_normalized}
            </h1>
            <WatchlistButton entityType="recipient" entityId={params.id} />
          </div>

          <div className="mt-5 grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-4">
            <Stat
              label="Total received"
              value={formatCurrencyFull(recipient.total_received)}
            />
            <Stat label="Awards" value={String(recipient.award_count)} />
            <Stat label="Largest award" value={formatCurrency(largest)} />
            <Stat
              label="Provinces"
              value={recipient.provinces.join(", ") || "—"}
            />
          </div>

          {topSectors.length > 0 && (
            <>
              <Separator className="my-6" />
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Funding by sector
              </p>
              <div className="flex flex-wrap gap-2">
                {topSectors.map(([s, total]) => (
                  <Badge key={s} variant="secondary">
                    {sectorLabel(s)} · {formatCurrency(total)}
                  </Badge>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {byYear.length > 1 && (
        <Card>
          <CardContent className="p-5">
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Funding by fiscal year
            </p>
            <div className="space-y-2.5">
              {byYear
                .slice()
                .sort((a, b) => a.year.localeCompare(b.year))
                .map((y) => (
                  <div key={y.year}>
                    <div className="flex justify-between text-xs">
                      <span className="tabular-nums">
                        {y.year}{" "}
                        <span className="text-muted-foreground">
                          ({y.count})
                        </span>
                      </span>
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

      <div>
        <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Award history
        </h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Select an award to view reference numbers, dates, source links, and
          related programs.
        </p>
        <RecipientTable awards={awards} />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}
