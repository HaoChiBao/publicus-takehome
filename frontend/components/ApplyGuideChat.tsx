"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Bot,
  ExternalLink,
  FileText,
  Loader2,
  MessageCircle,
  Send,
  User,
  X,
} from "lucide-react";
import {
  api,
  type ApplyGuideMessage,
  type ApplyGuideResult,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const AGENT_STEPS = [
  "Analyzing program requirements…",
  "Checking your company profile…",
  "Identifying required documents…",
  "Scanning for blockers…",
  "Preparing your application guide…",
];

function renderMarkdownLite(text: string) {
  const parts = text.split("\n");
  return parts.map((line, i) => {
    const html = line.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    return (
      <p
        key={i}
        className={cn("text-sm leading-relaxed", i > 0 && "mt-1.5")}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  });
}

export function useApplyGuide(programId: string) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [agentStep, setAgentStep] = useState(0);
  const [guide, setGuide] = useState<ApplyGuideResult | null>(null);
  const [messages, setMessages] = useState<ApplyGuideMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const stepTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (stepTimer.current) clearInterval(stepTimer.current);
    };
  }, []);

  const startGuide = useCallback(async () => {
    setOpen(true);
    setLoading(true);
    setError(null);
    setGuide(null);
    setMessages([]);
    setAgentStep(0);

    if (stepTimer.current) clearInterval(stepTimer.current);
    stepTimer.current = setInterval(() => {
      setAgentStep((s) => Math.min(s + 1, AGENT_STEPS.length - 1));
    }, 650);

    const sessionId =
      typeof window !== "undefined"
        ? localStorage.getItem("publicus_session") ?? undefined
        : undefined;

    try {
      const res = await api.programApplyGuide(programId, sessionId);
      setGuide(res);
      setMessages(res.messages);
    } catch {
      setError("Could not generate the application guide. Is the API running?");
    } finally {
      if (stepTimer.current) clearInterval(stepTimer.current);
      setLoading(false);
    }
  }, [programId]);

  const close = useCallback(() => setOpen(false), []);

  const handleSend = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const text = input.trim();
      if (!text || sending) return;

      const userMsg: ApplyGuideMessage = { role: "user", content: text };
      const nextHistory = [...messages, userMsg];
      setMessages(nextHistory);
      setInput("");
      setSending(true);

      const sessionId = localStorage.getItem("publicus_session") ?? undefined;
      try {
        const res = await api.programApplyChat(
          programId,
          text,
          sessionId,
          nextHistory
        );
        let content = res.answer;
        if (res.link?.href) {
          content += `\n\n**${res.link.label}:** ${res.link.href}`;
        }
        setMessages((m) => [...m, { role: "assistant", content }]);
      } catch {
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            content:
              "Sorry, I couldn't answer that. Try again or check the official application portal.",
          },
        ]);
      } finally {
        setSending(false);
      }
    },
    [input, sending, messages, programId]
  );

  return {
    open,
    loading,
    agentStep,
    agentSteps: AGENT_STEPS,
    guide,
    messages,
    input,
    setInput,
    sending,
    error,
    startGuide,
    close,
    handleSend,
  };
}

export function ApplyGuideTrigger({
  onClick,
  loading,
}: {
  onClick: () => void;
  loading?: boolean;
}) {
  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={loading}>
      {loading ? (
        <Loader2 className="size-4 animate-spin" />
      ) : (
        <MessageCircle className="size-4" />
      )}
      How do I apply?
    </Button>
  );
}

export function ApplyGuidePanel({
  programName,
  guide,
  open,
  loading,
  agentStep,
  agentSteps,
  messages,
  input,
  setInput,
  sending,
  error,
  close,
  handleSend,
}: {
  programName: string;
  open: boolean;
} & ReturnType<typeof useApplyGuide>) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      scrollRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [open]);

  useEffect(() => {
    scrollRef.current
      ?.querySelector("[data-chat-scroll]")
      ?.scrollTo({ top: 99999, behavior: "smooth" });
  }, [messages, loading, sending]);

  if (!open) return null;

  return (
    <Card
      ref={scrollRef}
      id="apply-guide-panel"
      className="border-primary/20 shadow-md"
    >
      <CardContent className="flex flex-col p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <Bot className="size-5 text-primary" />
            <div>
              <p className="text-sm font-semibold">How to apply</p>
              <p className="text-xs text-muted-foreground line-clamp-1">
                {programName}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {guide && (
              <Badge variant="outline" className="tabular-nums text-[10px]">
                {Math.round(guide.readiness_score * 100)}% ready
              </Badge>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={close}
              aria-label="Close guide"
            >
              <X className="size-4" />
            </Button>
          </div>
        </div>

        <div className="grid gap-0 lg:grid-cols-[1fr_16rem]">
          <div
            data-chat-scroll
            className="max-h-[min(28rem,60vh)] space-y-3 overflow-y-auto px-4 py-4"
          >
            {loading && (
              <div className="flex items-start gap-3 rounded-lg bg-muted/50 p-3">
                <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-primary" />
                <div>
                  <p className="text-sm font-medium">Building your guide…</p>
                  <p className="text-xs text-muted-foreground">
                    {agentSteps[agentStep]}
                  </p>
                </div>
              </div>
            )}

            {error && (
              <p className="text-sm font-medium text-destructive">{error}</p>
            )}

            {!loading &&
              messages.map((msg, i) => (
                <div
                  key={i}
                  className={cn(
                    "flex gap-2",
                    msg.role === "user" ? "justify-end" : "justify-start"
                  )}
                >
                  {msg.role === "assistant" && (
                    <Bot className="mt-1 size-4 shrink-0 text-muted-foreground" />
                  )}
                  <div
                    className={cn(
                      "max-w-[90%] rounded-lg px-3 py-2",
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted/60"
                    )}
                  >
                    {msg.role === "user" ? (
                      <p className="text-sm">{msg.content}</p>
                    ) : (
                      renderMarkdownLite(msg.content)
                    )}
                  </div>
                  {msg.role === "user" && (
                    <User className="mt-1 size-4 shrink-0 text-muted-foreground" />
                  )}
                </div>
              ))}

            {sending && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Thinking…
              </div>
            )}

            {guide && !loading && guide.links.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {guide.links.map((link) => (
                  <a
                    key={link.href}
                    href={link.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted"
                  >
                    {link.label}
                    <ExternalLink className="size-3 opacity-60" />
                  </a>
                ))}
              </div>
            )}
          </div>

          {guide && !loading && (
            <aside className="space-y-4 border-t px-4 py-4 lg:border-l lg:border-t-0">
              {guide.blockers.length > 0 && (
                <div>
                  <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-destructive">
                    <AlertTriangle className="size-3.5" />
                    Blockers
                  </p>
                  <ul className="space-y-1 text-sm">
                    {guide.blockers.map((b) => (
                      <li key={b} className="text-destructive/90">
                        {b}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {guide.warnings.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-700">
                    Warnings
                  </p>
                  <ul className="space-y-1 text-sm text-muted-foreground">
                    {guide.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              {guide.steps.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Steps
                  </p>
                  <ol className="space-y-2 text-sm">
                    {guide.steps.map((s) => (
                      <li key={s.order}>
                        <span className="font-medium">
                          {s.order}. {s.title}
                        </span>
                        <p className="text-xs text-muted-foreground">
                          {s.detail}
                        </p>
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              {guide.documents.length > 0 && (
                <div>
                  <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <FileText className="size-3.5" />
                    Documents
                  </p>
                  <ul className="space-y-1.5 text-sm">
                    {guide.documents.map((d) => (
                      <li key={d.name}>
                        <span className="font-medium">{d.name}</span>
                        {d.required && (
                          <Badge
                            variant="outline"
                            className="ml-1.5 text-[10px]"
                          >
                            required
                          </Badge>
                        )}
                        <p className="text-xs text-muted-foreground">
                          {d.detail}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </aside>
          )}
        </div>

        <form
          onSubmit={handleSend}
          className="flex gap-2 border-t px-4 py-3"
        >
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about deadlines, documents, eligibility…"
            disabled={loading || !!error}
            className="flex-1"
          />
          <Button
            type="submit"
            size="sm"
            disabled={loading || sending || !input.trim() || !!error}
          >
            <Send className="size-4" />
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function ApplyGuideChat({
  programId,
  programName,
}: {
  programId: string;
  programName: string;
}) {
  const guide = useApplyGuide(programId);
  return (
    <>
      <ApplyGuideTrigger onClick={guide.startGuide} loading={guide.loading} />
      <ApplyGuidePanel programName={programName} {...guide} />
    </>
  );
}
