import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  province: boolean;
  sector: boolean;
  size: boolean;
  hasHistory: boolean;
}

function Chip({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium",
        ok
          ? "border-foreground/20 bg-foreground text-background"
          : "border-input bg-background text-muted-foreground"
      )}
    >
      {ok ? <Check className="size-3" /> : <X className="size-3" />}
      {label}
    </span>
  );
}

export default function MatchScore({ province, sector, size, hasHistory }: Props) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <Chip label="Province" ok={province} />
      <Chip label="Sector" ok={sector} />
      <Chip label="Size" ok={size} />
      <Chip label="Recently awarded" ok={hasHistory} />
    </div>
  );
}
