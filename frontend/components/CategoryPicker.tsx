"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Plus } from "lucide-react";
import { api, type Category } from "@/lib/api";
import { CategoryDialog } from "./CategoryDialog";

/** Button + menu listing categories, with "New category…". Calls onPick with the chosen category. */
export function CategoryPicker({
  label = "Move to…",
  onPick,
  documentIds,
  className = "",
  up = false,
}: {
  label?: string;
  onPick: (c: Category) => void;
  documentIds?: string[]; // when creating a new category, file these into it
  className?: string;
  up?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [cats, setCats] = useState<Category[] | null>(null);
  const [creating, setCreating] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const toggle = async () => {
    setOpen((o) => !o);
    if (!cats) setCats(await api<Category[]>("/categories"));
  };

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button onClick={toggle} className="flex items-center gap-1.5 rounded-lg border border-line bg-card px-3 py-2 text-xs hover:bg-white">
        {label} <ChevronDown className="h-3 w-3" />
      </button>
      {open && (
        <div className={`absolute right-0 z-30 w-60 rounded-lg border border-line bg-card p-1 shadow-lg ${up ? "bottom-full mb-1" : "mt-1"}`}>
          <div className="max-h-64 overflow-y-auto">
            {cats === null && <p className="p-2 text-xs text-muted">Loading…</p>}
            {cats?.map((c) => (
              <button
                key={c.id}
                onClick={() => {
                  onPick(c);
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-background"
              >
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: c.color }} />
                <span className="truncate">{c.name}</span>
                <span className="ml-auto font-mono text-[10px] text-muted">{c.count}</span>
              </button>
            ))}
          </div>
          <button
            onClick={() => {
              setCreating(true);
              setOpen(false);
            }}
            className="mt-1 flex w-full items-center gap-2 rounded border-t border-line px-2 py-2 text-left text-xs text-ink hover:bg-background"
          >
            <Plus className="h-3.5 w-3.5" /> New category…
          </button>
        </div>
      )}
      {creating && (
        <CategoryDialog
          open
          onClose={() => setCreating(false)}
          documentIds={documentIds}
          onSaved={(c) => {
            setCats(null);
            if (!documentIds?.length) onPick(c);
            else onPick({ ...c, id: "__created__" });
          }}
        />
      )}
    </div>
  );
}
