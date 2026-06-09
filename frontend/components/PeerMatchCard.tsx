import Link from "next/link";
import type { PeerCompany } from "@/lib/api";
import { formatCurrencyFull } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export default function PeerMatchCard({ peer }: { peer: PeerCompany }) {
  return (
    <Link href={`/recipients/${peer.id}`} className="block">
      <Card className="h-full transition-colors hover:border-foreground">
        <CardContent className="p-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold leading-tight">{peer.name}</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {peer.city ? `${peer.city}, ` : ""}
                {peer.province || "—"}
              </p>
            </div>
            <Badge className="shrink-0 tabular-nums">
              {Math.round(peer.similarity_score * 100)}% match
            </Badge>
          </div>
          <p className="mt-2 text-xs font-medium tabular-nums">
            {formatCurrencyFull(peer.total_amount)} · {peer.award_count} awards
          </p>
          {peer.match_reasons.length > 0 && (
            <p className="mt-1.5 text-xs text-muted-foreground">
              {peer.match_reasons.join(" · ")}
            </p>
          )}
          {peer.programs_in_common.length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground truncate">
              Won: {peer.programs_in_common.slice(0, 2).join(", ")}
            </p>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
