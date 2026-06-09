"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Program, type RecipientHit } from "@/lib/api";
import { formatCurrencyFull } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import WatchlistButton from "@/components/WatchlistButton";

export default function WatchlistPage() {
  const router = useRouter();
  const [programs, setPrograms] = useState<Program[]>([]);
  const [recipients, setRecipients] = useState<RecipientHit[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const session = localStorage.getItem("publicus_session");
    if (!session) {
      router.push("/");
      return;
    }
    api
      .getWatchlist(session)
      .then((w) => {
        setPrograms(w.programs);
        setRecipients(w.recipients);
      })
      .finally(() => setLoading(false));
  }, [router]);

  if (loading)
    return (
      <div className="mx-auto max-w-3xl space-y-3">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold tracking-tight">My Watchlist</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Saved grant programs and competitor companies you want to track.
      </p>

      <section className="mt-8">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Programs ({programs.length})
        </h2>
        {programs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No saved programs yet.</p>
        ) : (
          <div className="space-y-2">
            {programs.map((p) => (
              <Card key={p.id}>
                <CardContent className="flex items-center justify-between p-4">
                  <Link href={`/program/${p.id}`} className="hover:underline">
                    <h3 className="font-semibold">{p.name}</h3>
                    <p className="text-xs text-muted-foreground">{p.department}</p>
                  </Link>
                  <WatchlistButton entityType="program" entityId={p.id} />
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section className="mt-8">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Competitors ({recipients.length})
        </h2>
        {recipients.length === 0 ? (
          <p className="text-sm text-muted-foreground">No saved companies yet.</p>
        ) : (
          <div className="space-y-2">
            {recipients.map((r) => (
              <Card key={r.id}>
                <CardContent className="flex items-center justify-between p-4">
                  <Link href={`/recipients/${r.id}`} className="hover:underline">
                    <h3 className="font-semibold">{r.name}</h3>
                    <p className="text-xs text-muted-foreground">
                      {formatCurrencyFull(r.total_amount)} · {r.award_count} awards
                    </p>
                  </Link>
                  <WatchlistButton entityType="recipient" entityId={r.id} />
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
