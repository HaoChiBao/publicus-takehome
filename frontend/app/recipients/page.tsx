"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { api, type RecipientHit } from "@/lib/api";
import { formatCurrencyFull } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

export default function RecipientSearchPage() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<RecipientHit[]>([]);
  const [loading, setLoading] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setLoading(true);
      api
        .searchRecipients(q)
        .then((d) => setResults(d.recipients))
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [q]);

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold tracking-tight">Recipient Search</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Search any company to see its full federal grant history — the
        competitor intelligence view.
      </p>

      <div className="relative mt-4">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search company name…"
          className="h-11 pl-9 text-base"
        />
      </div>

      <div className="mt-4 space-y-2">
        {loading && (
          <>
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </>
        )}
        {!loading && results.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {q ? "No companies found." : "Start typing to search recipients."}
          </p>
        )}
        {!loading &&
          results.map((r) => (
            <Link key={r.id} href={`/recipients/${r.id}`} className="block">
              <Card className="transition-colors hover:border-foreground">
                <CardContent className="flex items-center justify-between p-4">
                  <div>
                    <h3 className="font-semibold">{r.name}</h3>
                    <p className="text-xs text-muted-foreground">
                      {r.city ? `${r.city}, ` : ""}
                      {r.province || "—"}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold tabular-nums">
                      {formatCurrencyFull(r.total_amount)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {r.award_count} awards
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
