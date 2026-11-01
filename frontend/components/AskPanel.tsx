"use client";

import Link from "next/link";
import { useState } from "react";
import { Loader2, Send, Sparkles } from "lucide-react";
import { api, json, type AskResult } from "@/lib/api";

type Turn = { role: "user" | "assistant"; content: string; result?: AskResult };

export function AskPanel({
  scope,
  title = "Ask about this",
  suggestions = [],
  placeholder = "Ask a question…",
}: {
  scope: { document_ids?: string[]; project_id?: string };
  title?: string;
  suggestions?: string[];
  placeholder?: string;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  const ask = async (question: string) => {
    if (!question.trim() || busy) return;
    const history = turns.map(({ role, content }) => ({ role, content }));
    setTurns((t) => [...t, { role: "user", content: question }]);
    setInput("");
    setBusy(true);
    try {
      const result = await api<AskResult>("/ask", json("POST", { question, history, ...scope }));
      setTurns((t) => [...t, { role: "assistant", content: result.answer, result }]);
    } catch (e) {
      setTurns((t) => [...t, { role: "assistant", content: `Something went wrong: ${(e as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="flex h-fit flex-col rounded-xl border border-line bg-card md:sticky md:top-6">
      <header className="flex items-center gap-2 border-b border-line px-4 py-3">
        <Sparkles className="h-4 w-4 text-accent" />
        <h2 className="font-serif text-lg">{title}</h2>
      </header>

      <div className="max-h-[60vh] min-h-48 space-y-3 overflow-y-auto p-4 text-sm">
        {turns.length === 0 && (
          <>
            <p className="text-muted">Answers cite the documents they come from.</p>
            <div className="flex flex-wrap gap-2">
              {suggestions.map((s) => (
                <button key={s} onClick={() => ask(s)} className="rounded-full border border-line px-3 py-1 text-xs text-muted hover:border-ink hover:text-ink">
                  {s}
                </button>
              ))}
            </div>
          </>
        )}
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "flex justify-end" : ""}>
            <div className={`max-w-[90%] whitespace-pre-wrap rounded-lg px-3 py-2 ${t.role === "user" ? "bg-ink text-white" : "bg-[#eef4ef]"}`}>
              {t.content}
              {!!t.result?.sources.length && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {t.result.sources.map((s) => (
                    <Link
                      key={s.n}
                      href={`/photo/${s.document_id}`}
                      title={s.text}
                      className="rounded bg-white px-1.5 py-0.5 font-mono text-[10px] uppercase text-muted hover:text-ink"
                    >
                      [{s.n}] {s.title}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && <Loader2 className="h-4 w-4 animate-spin text-muted" />}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
        className="flex items-center gap-2 border-t border-line p-3"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={placeholder}
          className="flex-1 rounded-md border border-line bg-background px-3 py-2 text-sm outline-none focus:border-ink"
        />
        <button aria-label="Send" disabled={busy} className="grid h-9 w-9 place-items-center rounded-md bg-ink text-white disabled:opacity-50">
          <Send className="h-4 w-4" />
        </button>
      </form>
    </section>
  );
}
