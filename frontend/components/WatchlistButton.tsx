"use client";

import { useEffect, useState } from "react";
import { Star } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function WatchlistButton({
  entityType,
  entityId,
}: {
  entityType: "program" | "recipient";
  entityId: string;
}) {
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const session = localStorage.getItem("publicus_session");
    if (!session) return;
    api
      .getWatchlist(session)
      .then((w) => {
        const ids =
          entityType === "program"
            ? w.programs.map((p) => p.id)
            : w.recipients.map((r) => r.id);
        setSaved(ids.includes(entityId));
      })
      .catch(() => {});
  }, [entityType, entityId]);

  async function toggle() {
    const session = localStorage.getItem("publicus_session");
    if (!session) return;
    setLoading(true);
    try {
      if (saved) {
        await api.removeWatchlist(session, entityType, entityId);
        setSaved(false);
      } else {
        await api.addWatchlist(session, entityType, entityId);
        setSaved(true);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      disabled={loading}
      onClick={toggle}
      className="gap-1.5"
    >
      <Star
        className={cn("size-4", saved && "fill-amber-400 text-amber-500")}
      />
      {saved ? "Saved" : "Save"}
    </Button>
  );
}
