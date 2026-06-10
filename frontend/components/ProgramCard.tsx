import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import type { Program } from "@/lib/api";
import { amountRange, formatCurrency } from "@/lib/format";
import { cacheProgram } from "@/lib/programCache";
import MatchScore from "@/components/MatchScore";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export default function ProgramCard({
  program: p,
  showMatch = true,
  compact = false,
}: {
  program: Program;
  showMatch?: boolean;
  compact?: boolean;
}) {
  const summary =
    p.summary_1liner || p.short_description || p.description;
  const stats = p.stats;
  const hasAwardHistory = (stats?.award_count ?? 0) > 0;

  if (!p.id) {
    return null;
  }

  return (
    <Link
      href={`/program/${p.id}`}
      className="block"
      onClick={() => cacheProgram(p)}
    >
      <Card className="transition-colors hover:border-foreground">
        <CardContent className={compact ? "space-y-2 p-4" : "space-y-3 p-4"}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="font-semibold leading-tight">{p.name}</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {p.department}
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
              {showMatch && p.score !== undefined && p.score > 0 && (
                <Badge className="tabular-nums">
                  {Math.round(p.score * 100)}% match
                </Badge>
              )}
              {p.is_open === false && (
                <Badge variant="outline">Closed</Badge>
              )}
            </div>
          </div>

          {summary && (
            <p
              className={
                compact
                  ? "line-clamp-2 text-sm text-muted-foreground"
                  : "line-clamp-3 text-sm leading-relaxed text-muted-foreground"
              }
            >
              {summary}
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
            {hasAwardHistory && (
              <>
                <Badge variant="outline" className="tabular-nums">
                  {formatCurrency(stats?.total_disbursed)} disbursed
                </Badge>
                <Badge variant="outline" className="tabular-nums">
                  {stats?.award_count} awards · {stats?.recipient_count}{" "}
                  recipients
                </Badge>
                {stats?.median_award != null && stats.median_award > 0 && (
                  <Badge variant="outline" className="tabular-nums">
                    Median {formatCurrency(stats.median_award)}
                  </Badge>
                )}
              </>
            )}
          </div>

          {p.keywords && p.keywords.length > 0 && !compact && (
            <div className="flex flex-wrap gap-1">
              {p.keywords.slice(0, 5).map((kw) => (
                <Badge key={kw} variant="muted" className="text-[10px] font-normal">
                  {kw}
                </Badge>
              ))}
            </div>
          )}

          {showMatch && p.match && (
            <MatchScore
              province={p.match.province}
              sector={p.match.sector}
              size={p.match.size}
              naics={p.match.naics}
              activities={p.match.activities}
              hasHistory={p.match.hasHistory}
            />
          )}

          {showMatch && p.match_reasons && p.match_reasons.length > 0 && (
            <ul className="space-y-0.5 border-t pt-2 text-xs text-muted-foreground">
              {p.match_reasons.slice(0, 3).map((r) => (
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
