"use client";

import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  X, Send, ChevronDown, Lock, Loader2,
  Download, RotateCcw, ExternalLink,
} from "lucide-react";
import Image from "next/image";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import Link from "next/link";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ConvMessage {
  role: "user" | "assistant";
  content: string;
}

interface Message extends ConvMessage {
  sql?: string;
  rowCount?: number;
  rows?: Record<string, unknown>[];
  columns?: string[];
  error?: boolean;
  /** optional page shortcut to show below the answer */
  navHint?: { label: string; href: string };
}

interface AIAccessStatus {
  has_access: boolean;
  reason?: string;
}

interface BIQueryResponse {
  answer: string;
  sql: string;
  row_count: number;
  rows: Record<string, unknown>[];
  columns: string[];
  provider: string;
}

// ── Suggested prompts ─────────────────────────────────────────────────────────

const SUGGESTIONS = [
  { label: "Status overview", prompt: "Give me a complete status overview of all supplier advance payment requests" },
  { label: "Pending payments", prompt: "Which requests are still pending payment and how old are they?" },
  { label: "Overdue shipments", prompt: "Show all overdue or critical shipments with their supplier names" },
  { label: "Cost of fund", prompt: "What is the total cost of fund and which requests contribute the most?" },
  { label: "Defaulted suppliers", prompt: "Are there any defaulted suppliers? Show details." },
  { label: "Payment report", prompt: "Generate a full payment report with all processed payments" },
  { label: "Top suppliers", prompt: "Which suppliers have the highest total deposit amount?" },
  { label: "This month", prompt: "How many new requests were submitted this month and what is the total deposit value?" },
];

// ── Nav hints — shown after relevant answers ──────────────────────────────────

function guessNavHint(question: string): { label: string; href: string } | undefined {
  const q = question.toLowerCase();
  if (q.includes("analytic") || q.includes("overdue") || q.includes("cost of fund"))
    return { label: "Open Analytics", href: "/analytics" };
  if (q.includes("default") || q.includes("supplier risk") || q.includes("flagged"))
    return { label: "Open Supplier Risk", href: "/finance" };
  if (q.includes("report") || q.includes("export") || q.includes("download"))
    return { label: "Open Reports", href: "/reports" };
  if (q.includes("user") || q.includes("access") || q.includes("admin"))
    return { label: "Open Admin", href: "/admin" };
  return undefined;
}

// ── CSV export ────────────────────────────────────────────────────────────────

function downloadCSV(rows: Record<string, unknown>[], columns: string[], filename = "report.csv") {
  const escape = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return s.includes(",") || s.includes('"') || s.includes("\n")
      ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [
    columns.join(","),
    ...rows.map((r) => columns.map((c) => escape(r[c])).join(",")),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── API calls ─────────────────────────────────────────────────────────────────

async function checkAccess(): Promise<AIAccessStatus> {
  const res = await api.get("/ai/access");
  return res.data;
}

async function askQuestion(payload: {
  question: string;
  history: ConvMessage[];
}): Promise<BIQueryResponse> {
  const res = await api.post("/ai/query", payload);
  return res.data;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function BIChat() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [showSQL, setShowSQL] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: access, isLoading: accessLoading } = useQuery({
    queryKey: ["ai-access"],
    queryFn: checkAccess,
    staleTime: 30_000,
  });

  const mutation = useMutation({
    mutationFn: askQuestion,
    onSuccess: (data, variables) => {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          sql: data.sql,
          rowCount: data.row_count,
          rows: data.rows,
          columns: data.columns,
          navHint: guessNavHint(variables.question),
        },
      ]);
    },
    onError: (err: any) => {
      const msg = err?.message || "Something went wrong. Try rephrasing.";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: msg, error: true },
      ]);
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open]);

  function buildHistory(): ConvMessage[] {
    // Send the last 10 turns (20 messages) so the AI has recent context
    return messages.slice(-20).map((m) => ({ role: m.role, content: m.content }));
  }

  function handleSend(question?: string) {
    const q = (question ?? input).trim();
    if (!q || mutation.isPending) return;
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setInput("");
    mutation.mutate({ question: q, history: buildHistory() });
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleReset() {
    setMessages([]);
    setInput("");
  }

  if (!user) return null;

  return (
    <>
      {/* Floating toggle button */}
      <button
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "fixed bottom-6 right-4 sm:right-6 z-50 h-12 w-12 items-center justify-center rounded-full shadow-lg transition-all duration-200",
          "bg-primary text-primary-foreground hover:bg-primary/90",
          open ? "hidden sm:flex" : "flex",
          open && "rotate-12"
        )}
        title="AI BI Assistant"
      >
        <Image src="/logo.png" alt="AI Assistant" width={28} height={28} className="object-contain" />
      </button>

      {/* Chat panel — full-screen on mobile, floating panel on desktop */}
      {open && (
        <div className={cn(
          "fixed z-50 flex flex-col bg-background shadow-2xl overflow-hidden border",
          "inset-x-0 bottom-0 top-16 rounded-t-2xl",
          "sm:inset-auto sm:bottom-20 sm:right-6 sm:w-[400px] sm:max-h-[600px] sm:rounded-xl sm:top-auto"
        )}>
          {/* Header */}
          <div className="flex items-center justify-between border-b px-4 py-3 bg-primary text-primary-foreground shrink-0">
            <div className="flex items-center gap-2">
              <Image src="/logo.png" alt="Logo" width={20} height={20} className="object-contain brightness-0 invert" />
              <span className="text-sm font-semibold">BI Assistant</span>
              {access?.has_access && (
                <span className="text-[10px] bg-primary-foreground/20 px-1.5 py-0.5 rounded-full uppercase tracking-wide">
                  AI
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              {messages.length > 0 && (
                <button
                  onClick={handleReset}
                  title="Clear conversation"
                  className="p-1.5 hover:bg-primary-foreground/20 rounded transition-colors"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="p-1.5 hover:bg-primary-foreground/20 rounded transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-[320px]">
            {accessLoading ? (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
              </div>
            ) : !access?.has_access ? (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-4">
                <Lock className="h-8 w-8 text-muted-foreground" />
                <p className="text-sm font-medium">Access Restricted</p>
                <p className="text-xs text-muted-foreground">{access?.reason}</p>
              </div>
            ) : (
              <>
                {messages.length === 0 && (
                  <div className="space-y-2">
                    <p className="text-xs text-muted-foreground text-center pt-1 pb-1">
                      Ask anything about deposits, suppliers, payments, or analytics.
                    </p>
                    <div className="grid grid-cols-2 gap-1.5">
                      {SUGGESTIONS.map((s) => (
                        <button
                          key={s.label}
                          onClick={() => handleSend(s.prompt)}
                          className="text-left text-xs border rounded-lg px-2.5 py-2 hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                        >
                          {s.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {messages.map((msg, i) => (
                  <div
                    key={i}
                    className={cn(
                      "flex flex-col",
                      msg.role === "user" ? "items-end" : "items-start"
                    )}
                  >
                    <div
                      className={cn(
                        "max-w-[88%] rounded-xl px-3 py-2 text-sm",
                        msg.role === "user"
                          ? "bg-primary text-primary-foreground rounded-br-none"
                          : msg.error
                          ? "bg-destructive/10 text-destructive border border-destructive/20 rounded-bl-none"
                          : "bg-muted text-foreground rounded-bl-none"
                      )}
                    >
                      {msg.role === "assistant" ? (
                        <div className="prose prose-sm max-w-none dark:prose-invert leading-relaxed [&>p]:mb-1 [&>ul]:mb-1 [&>ul]:pl-4 [&>li]:mb-0.5 prose-p:text-foreground prose-li:text-foreground prose-strong:text-foreground">
                          <ReactMarkdown>{msg.content}</ReactMarkdown>
                        </div>
                      ) : (
                        <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                      )}

                      {/* SQL viewer */}
                      {msg.sql && (
                        <div className="mt-2 border-t border-border/40 pt-2">
                          <button
                            onClick={() => setShowSQL(showSQL === i ? null : i)}
                            className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                          >
                            <ChevronDown
                              className={cn(
                                "h-3 w-3 transition-transform",
                                showSQL === i && "rotate-180"
                              )}
                            />
                            {msg.rowCount} rows · View SQL
                          </button>
                          {showSQL === i && (
                            <pre className="mt-1 text-[10px] bg-background/60 rounded p-2 overflow-x-auto text-muted-foreground whitespace-pre-wrap">
                              {msg.sql}
                            </pre>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Action bar below assistant messages */}
                    {msg.role === "assistant" && !msg.error && (
                      <div className="flex items-center gap-2 mt-1 px-1">
                        {/* CSV download */}
                        {msg.rows && msg.rows.length > 0 && msg.columns && (
                          <button
                            onClick={() =>
                              downloadCSV(
                                msg.rows!,
                                msg.columns!,
                                `bi-report-${Date.now()}.csv`
                              )
                            }
                            className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors border rounded px-2 py-0.5"
                          >
                            <Download className="h-3 w-3" />
                            Download CSV ({msg.rowCount} rows)
                          </button>
                        )}
                        {/* Nav hint */}
                        {msg.navHint && (
                          <Link
                            href={msg.navHint.href}
                            className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors border rounded px-2 py-0.5"
                          >
                            <ExternalLink className="h-3 w-3" />
                            {msg.navHint.label}
                          </Link>
                        )}
                      </div>
                    )}
                  </div>
                ))}

                {mutation.isPending && (
                  <div className="flex justify-start">
                    <div className="bg-muted rounded-xl rounded-bl-none px-3 py-2">
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    </div>
                  </div>
                )}

                <div ref={bottomRef} />
              </>
            )}
          </div>

          {/* Input */}
          {access?.has_access && (
            <div className="border-t p-3 flex gap-2 shrink-0">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Ask a question or request a report…"
                rows={1}
                className="flex-1 resize-none text-sm bg-muted rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-primary placeholder:text-muted-foreground"
                style={{ maxHeight: 80 }}
              />
              <Button
                size="icon"
                onClick={() => handleSend()}
                disabled={!input.trim() || mutation.isPending}
                className="shrink-0 h-9 w-9"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
