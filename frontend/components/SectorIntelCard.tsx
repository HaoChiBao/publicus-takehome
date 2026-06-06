// Hero intelligence card: headline number, top-programs bar chart (CSS),
// year-over-year sparkline (inline SVG), and top recipients. Monochrome.
import type { SectorSummary } from "@/lib/api";
import { formatCurrency, formatCurrencyFull } from "@/lib/format";
import { sectorLabel } from "@/lib/constants";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

function Sparkline({ data }: { data: { year: string; total: number }[] }) {
  if (data.length < 2) return null;
  const w = 220;
  const h = 48;
  const max = Math.max(...data.map((d) => d.total), 1);
  const step = w / (data.length - 1);
  const pts = data
    .map((d, i) => `${i * step},${h - (d.total / max) * (h - 6) - 3}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline
        points={pts}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        className="text-foreground"
      />
      {data.map((d, i) => (
        <circle
          key={d.year}
          cx={i * step}
          cy={h - (d.total / max) * (h - 6) - 3}
          r="2.5"
          className="fill-foreground"
        />
      ))}
    </svg>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-0.5 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}

export default function SectorIntelCard({ summary }: { summary: SectorSummary }) {
  const max = Math.max(...summary.top_programs.map((p) => p.total), 1);
  const provinceLabel = summary.province
    ? `in ${summary.province}`
    : "across Canada";

  return (
    <Card>
      <CardHeader className="pb-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Sector Intelligence
        </p>
        <CardTitle className="text-2xl font-bold leading-snug">
          {sectorLabel(summary.sector)} firms {provinceLabel} received{" "}
          {formatCurrency(summary.total_amount)} in grants over the last 2 fiscal
          years
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-wrap gap-8">
          <Stat label="Total disbursed" value={formatCurrencyFull(summary.total_amount)} />
          <Stat label="Awards" value={String(summary.award_count)} />
          <Stat label="Average award" value={formatCurrencyFull(summary.avg_amount)} />
        </div>

        <Separator />

        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <div className="md:col-span-2">
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Top programs by total awards
            </p>
            {summary.top_programs.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No award data for this segment yet.
              </p>
            )}
            <div className="space-y-2.5">
              {summary.top_programs.map((p) => (
                <div key={p.name}>
                  <div className="flex justify-between gap-2 text-xs">
                    <span className="truncate">{p.name}</span>
                    <span className="font-medium tabular-nums">
                      {formatCurrency(p.total)}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-muted">
                    <div
                      className="h-1.5 rounded-full bg-foreground"
                      style={{ width: `${(p.total / max) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              By fiscal year
            </p>
            <Sparkline data={summary.by_fiscal_year} />
            <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
              {summary.by_fiscal_year.map((d) => (
                <span key={d.year}>{d.year}</span>
              ))}
            </div>
          </div>
        </div>

        {summary.top_recipients.length > 0 && (
          <>
            <Separator />
            <div>
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Top recipients
              </p>
              <div className="flex flex-wrap gap-2">
                {summary.top_recipients.map((r) => (
                  <span
                    key={r.name}
                    className="inline-flex items-center gap-1.5 rounded-md border bg-muted px-2.5 py-1 text-xs"
                  >
                    {r.name}
                    <span className="font-medium tabular-nums text-muted-foreground">
                      {formatCurrencyFull(r.total)}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
