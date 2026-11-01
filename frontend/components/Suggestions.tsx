"use client";

import { useState } from "react";
import { Check, Sparkles } from "lucide-react";
import { api, json, type Doc } from "@/lib/api";
import { useToast } from "./Toast";

/** Instead of "Uncategorized": one-click chips for the AI's suggested categories. */
export function SuggestionChips({ doc, onFiled, compact = false }: { doc: Doc; onFiled: (d: Doc) => void; compact?: boolean }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const list = doc.suggestions.slice(0, compact ? 1 : 3);
  if (!list.length) return <span className="eyebrow">Needs a category</span>;

  const accept = async (s: Doc["suggestions"][number]) => {
    setBusy(true);
    try {
      const body = s.category_id ? { category_id: s.category_id } : { new_category_name: s.name };
      const updated = await api<Doc>(`/documents/${doc.id}`, json("PATCH", body));
      toast(`Filed in “${updated.category?.name}”`);
      onFiled(updated);
    } catch (e) {
      toast((e as Error).message, { kind: "error" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="flex items-center gap-1 font-mono text-[10px] uppercase text-muted">
        <Sparkles className="h-3 w-3 text-accent" /> Suggested
      </span>
      {list.map((s) => (
        <button
          key={s.name}
          disabled={busy}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            accept(s);
          }}
          title={s.category_id ? `File in ${s.name}` : `Create “${s.name}” and file here`}
          className="relative z-10 flex items-center gap-1 rounded-full border border-dashed border-ink/40 px-2 py-0.5 text-[11px] text-ink hover:border-solid hover:bg-ink hover:text-white disabled:opacity-50"
        >
          <Check className="h-3 w-3" />
          {s.name}
          {!s.category_id && <span className="opacity-60">(new)</span>}
        </button>
      ))}
    </div>
  );
}
