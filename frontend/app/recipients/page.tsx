"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { api, type RecipientHit } from "@/lib/api";
import { PROVINCES } from "@/lib/constants";
import { formatCurrency, formatCurrencyFull } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

export default function RecipientSearchPage() {
  const [q, setQ] = useState("");
  const [province, setProvince] = useState("");
  const [results, setResults] = useState<RecipientHit[]>([]);
  const [loading, setLoading] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setLoading(true);
      api
        .searchRecipients(q, province || undefined)
        .then((d) => setResults(d.recipients))
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [q, province]);

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold tracking-tight">Recipient Search</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Search federal grant recipients by company name. View total funding,
        award counts, and full agreement history.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_180px]">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search company name…"
            className="h-11 pl-9 text-base"
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="recipient-province" className="sr-only">
            Province
          </Label>
          <Select
            id="recipient-province"
            value={province}
            onChange={(e) => setProvince(e.target.value)}
            className="h-11"
          >
            <option value="">All provinces</option>
            {PROVINCES.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {loading && (
          <>
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </>
        )}
        {!loading && results.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {q || province
              ? "No companies found."
              : "Start typing to search recipients."}
          </p>
        )}
        {!loading &&
          results.map((r) => (
            <Link key={r.id} href={`/recipients/${r.id}`} className="block">
              <Card className="transition-colors hover:border-foreground">
                <CardContent className="flex items-center justify-between gap-4 p-4">
                  <div className="min-w-0">
                    <h3 className="font-semibold leading-tight">{r.name}</h3>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {r.city ? `${r.city}, ` : ""}
                      {r.province || "—"}
                    </p>
                    {r.award_count > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <Badge variant="outline" className="tabular-nums">
                          {r.award_count} award{r.award_count === 1 ? "" : "s"}
                        </Badge>
                        {r.total_amount > 0 && (
                          <Badge variant="secondary" className="tabular-nums">
                            Avg {formatCurrency(r.total_amount / r.award_count)}
                          </Badge>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="font-semibold tabular-nums">
                      {formatCurrencyFull(r.total_amount)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      total received
                    </p>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
      </div>
    </div>
  );
}
