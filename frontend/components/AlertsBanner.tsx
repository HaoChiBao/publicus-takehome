import Link from "next/link";
import { AlertTriangle, Clock } from "lucide-react";
import type { DeadlineAlert } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export default function AlertsBanner({ alerts }: { alerts: DeadlineAlert[] }) {
  if (alerts.length === 0) return null;

  return (
    <Card className="border-amber-500/40 bg-amber-50/50 dark:bg-amber-950/20">
      <CardContent className="p-4">
        <div className="mb-3 flex items-center gap-2">
          <AlertTriangle className="size-4 text-amber-600" />
          <h2 className="text-sm font-semibold">Upcoming deadlines</h2>
          <Badge variant="secondary">{alerts.length}</Badge>
        </div>
        <div className="space-y-2">
          {alerts.map((a) => (
            <Link
              key={a.program_id}
              href={`/program/${a.program_id}`}
              className="flex items-center justify-between gap-3 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:border-foreground"
            >
              <span className="font-medium">{a.name}</span>
              <span className="flex items-center gap-2 shrink-0">
                <Badge
                  className={cn(
                    a.urgency === "critical" && "bg-red-600",
                    a.urgency === "warning" && "bg-amber-600",
                    a.urgency === "info" && "bg-blue-600"
                  )}
                >
                  <Clock className="mr-1 size-3" />
                  {a.days_remaining}d left
                </Badge>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {a.deadline}
                </span>
              </span>
            </Link>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
