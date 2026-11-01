"use client";

import Link from "next/link";
import { CheckCircle2, Circle, Star } from "lucide-react";
import { docDate, monthLabel, type Doc } from "@/lib/api";
import { Thumb } from "./Thumb";
import { SuggestionChips } from "./Suggestions";

type Props = {
  docs: Doc[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onChange?: (d: Doc) => void;
  groupByMonth?: boolean;
  snippets?: Record<string, string>;
};

/** Photo-library grid: month sections, tap to open, checkbox to select (selection mode = any selected). */
export function PhotoGrid({ docs, selected, onToggle, onChange, groupByMonth = true, snippets }: Props) {
  const groups: [string, Doc[]][] = [];
  for (const d of docs) {
    const key = groupByMonth ? monthLabel(docDate(d)) : "";
    const last = groups[groups.length - 1];
    if (last && last[0] === key) last[1].push(d);
    else groups.push([key, [d]]);
  }
  const selecting = selected.size > 0;

  return (
    <div className="space-y-6">
      {groups.map(([label, items]) => (
        <section key={label || "all"}>
          {label && <h3 className="eyebrow sticky top-0 z-10 -mx-1 mb-2 bg-background/90 px-1 py-1 backdrop-blur">{label}</h3>}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3 lg:grid-cols-4 xl:grid-cols-5">
            {items.map((d) => (
              <Tile
                key={d.id}
                doc={d}
                checked={selected.has(d.id)}
                selecting={selecting}
                onToggle={() => onToggle(d.id)}
                onChange={onChange}
                snippet={snippets?.[d.id]}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function Tile({
  doc,
  checked,
  selecting,
  onToggle,
  onChange,
  snippet,
}: {
  doc: Doc;
  checked: boolean;
  selecting: boolean;
  onToggle: () => void;
  onChange?: (d: Doc) => void;
  snippet?: string;
}) {
  const ready = doc.status === "ready";
  return (
    <div className={`group relative overflow-hidden rounded-xl border bg-card transition ${checked ? "border-ink ring-2 ring-ink" : "border-line hover:shadow-md"}`}>
      <Link
        href={`/photo/${doc.id}`}
        onClick={(e) => {
          if (selecting) {
            e.preventDefault();
            onToggle();
          }
        }}
        className="block"
      >
        <Thumb doc={doc} className="aspect-square w-full" />
      </Link>

      <button
        onClick={onToggle}
        aria-label={checked ? "Deselect" : "Select"}
        aria-pressed={checked}
        className={`absolute left-2 top-2 rounded-full bg-white/90 text-ink shadow transition ${
          selecting || checked ? "opacity-100" : "opacity-100 sm:opacity-0 sm:group-hover:opacity-100"
        }`}
      >
        {checked ? <CheckCircle2 className="h-5 w-5 fill-ink text-white" /> : <Circle className="h-5 w-5 text-ink/50" />}
      </button>
      {doc.favorite && <Star className="absolute right-2 top-2 h-4 w-4 fill-accent text-accent drop-shadow" />}

      <div className="space-y-1 p-2">
        <p className="truncate text-xs font-medium">{ready ? doc.title : doc.filename}</p>
        {snippet && <p className="line-clamp-2 text-[11px] text-muted">{snippet}</p>}
        {ready &&
          (doc.category ? (
            <span className="inline-flex max-w-full items-center gap-1 truncate text-[11px] text-muted">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: doc.category.color }} />
              <span className="truncate">{doc.category.name}</span>
            </span>
          ) : (
            onChange && <SuggestionChips doc={doc} onFiled={onChange} compact />
          ))}
        {!ready && <p className="font-mono text-[10px] uppercase text-muted">{doc.status}</p>}
      </div>
    </div>
  );
}
