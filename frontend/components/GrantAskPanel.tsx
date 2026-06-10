"use client";

import { useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { api, type GrantAskResult } from "@/lib/api";
import ProgramCard from "@/components/ProgramCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const SUGGESTIONS = [
  "R&D grants for software companies in Ontario",
  "Export funding for clean tech startups",
  "Hiring and wage subsidy programs",
  "SR&ED related tax credits",
  "Programs with recent award activity",
];

function renderAnswer(text: string) {
  const lines = text.split("\n");
  return lines.map((line, i) => {
    const trimmed = line.trim();
    if (!trimmed) return <br key={i} />;
    const bold = trimmed.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    if (trimmed.startsWith("•")) {
      return (
        <p
          key={i}
          className="text-sm leading-relaxed"
          dangerouslySetInnerHTML={{ __html: bold }}
        />
      );
    }
    return (
      <p
        key={i}
        className="text-sm leading-relaxed text-muted-foreground"
        dangerouslySetInnerHTML={{ __html: bold }}
      />
    );
  });
}

export default function GrantAskPanel({ sessionId }: { sessionId: string }) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GrantAskResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleAsk(q?: string) {
    const text = (q ?? question).trim();
    if (!text) return;
    setQuestion(text);
    setLoading(true);
    setError(null);
    try {
      const res = await api.askGrants(text, sessionId);
      setResult(res);
    } catch {
      setError("Could not run grant search. Is the API running?");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card className="border-dashed">
        <CardContent className="space-y-3 p-4">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Sparkles className="size-4 text-amber-600" />
            Ask in plain language
          </div>
          <p className="text-xs text-muted-foreground">
            Search across program names, eligibility, keywords, and award
            history — ranked for your company profile.
          </p>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              handleAsk();
            }}
          >
            <Input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. grants for hiring engineers in BC…"
              className="flex-1"
            />
            <Button type="submit" disabled={loading || !question.trim()}>
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                "Search"
              )}
            </Button>
          </form>
          <div className="flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => handleAsk(s)}
                className="rounded-full border px-2.5 py-0.5 text-xs text-muted-foreground transition-colors hover:border-foreground hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {error && (
        <p className="text-sm font-medium text-destructive">{error}</p>
      )}

      {result && (
        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-2 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Answer
              </p>
              <div className="space-y-1">{renderAnswer(result.answer)}</div>
              {result.insights.length > 0 && (
                <div className="mt-3 space-y-1 border-t pt-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Funding insights
                  </p>
                  {result.insights.map((ins, i) => (
                    <p key={i} className="text-sm text-muted-foreground">
                      {ins}
                    </p>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {result.programs.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Matching programs ({result.total})
              </p>
              <div className="space-y-3">
                {result.programs.map((p) => (
                  <ProgramCard key={p.id} program={p} compact />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
