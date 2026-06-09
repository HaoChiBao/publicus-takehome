import { Check, Circle, HelpCircle, X } from "lucide-react";
import type { ReadinessResult } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

function StatusIcon({ status }: { status: string }) {
  if (status === "pass") return <Check className="size-4 text-green-600" />;
  if (status === "fail") return <X className="size-4 text-red-600" />;
  if (status === "partial") return <Circle className="size-4 text-amber-500" />;
  return <HelpCircle className="size-4 text-muted-foreground" />;
}

export default function ReadinessChecklist({ data }: { data: ReadinessResult }) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Application readiness
          </h2>
          <span className="text-2xl font-bold tabular-nums">
            {Math.round(data.readiness_score * 100)}%
          </span>
        </div>

        <ul className="space-y-2">
          {data.items.map((item) => (
            <li
              key={item.key}
              className={cn(
                "flex items-start gap-2 text-sm",
                item.status === "fail" && "text-destructive"
              )}
            >
              <StatusIcon status={item.status} />
              <div>
                <span>{item.label}</span>
                {item.detail && (
                  <p className="text-xs text-muted-foreground">{item.detail}</p>
                )}
              </div>
            </li>
          ))}
        </ul>

        {data.blockers.length > 0 && (
          <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 p-3">
            <p className="text-xs font-semibold uppercase text-destructive">Blockers</p>
            <ul className="mt-1 space-y-0.5 text-sm">
              {data.blockers.map((b) => (
                <li key={b}>• {b}</li>
              ))}
            </ul>
          </div>
        )}

        {data.next_steps.length > 0 && (
          <div className="mt-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Next steps
            </p>
            <ul className="mt-1 space-y-0.5 text-sm text-muted-foreground">
              {data.next_steps.map((s) => (
                <li key={s}>→ {s}</li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
