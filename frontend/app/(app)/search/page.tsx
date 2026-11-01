"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { CalendarDays, Coins, Image as ImageIcon, Layers, Search, Sparkles } from "lucide-react";
import type { SearchFilters, SearchResult } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSelection } from "@/lib/selection";
import { PhotoGrid } from "@/components/PhotoGrid";
import { SelectionBar } from "@/components/SelectionBar";
import { AskPanel } from "@/components/AskPanel";

const EXAMPLES = ["warranty", "mountain in the background", "receipts over 40 euros", "photos from last summer", "person wearing a hoodie"];

const fmt = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

function FilterChips({ f }: { f: SearchFilters }) {
  const chips: { icon: React.ReactNode; text: string }[] = [];
  if (f.date_from || f.date_to)
    chips.push({ icon: <CalendarDays className="h-3 w-3" />, text: `${f.date_from ? fmt(f.date_from) : "…"} – ${f.date_to ? fmt(f.date_to) : "…"}` });
  if (f.kind) chips.push({ icon: <ImageIcon className="h-3 w-3" />, text: f.kind === "photo" ? "Photos" : "Documents" });
  if (f.category) chips.push({ icon: <Layers className="h-3 w-3" />, text: f.category });
  if (f.min_amount != null) chips.push({ icon: <Coins className="h-3 w-3" />, text: `over ${f.min_amount}` });
  if (f.max_amount != null) chips.push({ icon: <Coins className="h-3 w-3" />, text: `under ${f.max_amount}` });
  if (!chips.length) return null;
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
      <span className="eyebrow">Understood as</span>
      {f.semantic_query && <span className="rounded-full bg-ink px-2.5 py-1 text-white">“{f.semantic_query}”</span>}
      {chips.map((c) => (
        <span key={c.text} className="flex items-center gap-1 rounded-full border border-line bg-card px-2.5 py-1">
          {c.icon} {c.text}
        </span>
      ))}
      {f.parsed_by === "gemini" && (
        <span className="flex items-center gap-1 text-muted">
          <Sparkles className="h-3 w-3" /> Gemini
        </span>
      )}
    </div>
  );
}

export default function SearchPage() {
  const router = useRouter();
  const q = useSearchParams().get("q") ?? "";
  const { data, error } = useApi<SearchResult>(q ? `/search?q=${encodeURIComponent(q)}` : null);
  const sel = useSelection();
  const results = data?.results ?? [];
  const scopeIds = sel.selected.size ? sel.ids : results.map((h) => h.document.id);
  const go = (query: string) => {
    sel.clear();
    if (query.trim()) router.push(`/search?q=${encodeURIComponent(query.trim())}`);
  };

  return (
    <div className="mx-auto max-w-6xl">
      <p className="eyebrow mb-1">Semantic Search</p>
      <h1 className="mb-4 font-serif text-3xl md:text-4xl">Find anything</h1>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          go(String(new FormData(e.currentTarget).get("q") ?? ""));
        }}
        className="mb-3 flex items-center gap-3 rounded-xl border border-line bg-card px-4 py-3 focus-within:border-ink"
      >
        <Search className="h-4 w-4 shrink-0 text-muted" />
        <input
          key={q}
          name="q"
          defaultValue={q}
          autoFocus={!q}
          enterKeyHint="search"
          placeholder="Describe it: a place, an object, a date, an amount…"
          className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted"
        />
        <button className="rounded-lg bg-ink px-3 py-1.5 text-xs text-white">Search</button>
      </form>

      {!q && (
        <div className="mt-6">
          <p className="eyebrow mb-2">Try</p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button key={ex} onClick={() => go(ex)} className="rounded-full border border-line bg-card px-3 py-1.5 text-xs text-muted hover:border-ink hover:text-ink">
                {ex}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <p className="text-sm text-accent">{error}</p>}
      {q && !data && !error && <p className="eyebrow mt-4">Searching…</p>}
      {data && <FilterChips f={data.filters} />}

      {data && (
        <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
          <div className="min-w-0">
            <div className="mb-3 flex items-center justify-between text-xs text-muted">
              <span>
                {results.length} result{results.length === 1 ? "" : "s"}
                {sel.selected.size ? ` · ${sel.selected.size} selected` : ""}
              </span>
              {results.length > 0 && (
                <button onClick={() => (sel.selected.size ? sel.clear() : sel.selectAll(results.map((r) => r.document.id)))} className="hover:text-ink">
                  {sel.selected.size ? "Clear selection" : "Select all"}
                </button>
              )}
            </div>
            {results.length === 0 ? (
              <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">
                Nothing matched. Try fewer words or a broader description.
              </p>
            ) : (
              <PhotoGrid
                docs={results.map((r) => r.document)}
                snippets={Object.fromEntries(results.map((r) => [r.document.id, r.snippet]))}
                selected={sel.selected}
                onToggle={sel.toggle}
                groupByMonth={false}
              />
            )}
          </div>
          {results.length > 0 && (
            <div className="order-first lg:order-none">
              <AskPanel
                key={scopeIds.join(",")}
                scope={{ document_ids: scopeIds }}
                title={sel.selected.size ? `Ask about ${sel.selected.size} selected` : "Ask about these results"}
                placeholder="Narrow down, e.g. which one is for the Dyson?"
                suggestions={["Which of these are warranties?", "Summarize these"]}
              />
            </div>
          )}
        </div>
      )}

      <SelectionBar ids={sel.ids} onClear={sel.clear} onDone={() => router.refresh()} />
    </div>
  );
}
