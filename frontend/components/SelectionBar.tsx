"use client";

import { Star, Trash2, X } from "lucide-react";
import { api, json } from "@/lib/api";
import { AddToProject } from "./AddToProject";
import { CategoryPicker } from "./CategoryPicker";
import { useToast } from "./Toast";

/** Floating bulk-action bar; sits above the mobile tab bar. */
export function SelectionBar({ ids, onClear, onDone }: { ids: string[]; onClear: () => void; onDone: () => void }) {
  const toast = useToast();
  if (!ids.length) return null;

  const bulk = async (action: string, extra: object = {}, msg = "Done") => {
    try {
      await api("/documents/bulk", json("POST", { document_ids: ids, action, ...extra }));
      toast(msg);
      onClear();
      onDone();
    } catch (e) {
      toast((e as Error).message, { kind: "error" });
    }
  };

  return (
    <div className="fixed inset-x-2 bottom-20 z-30 mx-auto flex max-w-2xl flex-wrap items-center gap-2 rounded-2xl border border-line bg-card p-2 shadow-xl md:bottom-6">
      <button onClick={onClear} aria-label="Clear selection" className="rounded-lg p-2 text-muted hover:text-ink">
        <X className="h-4 w-4" />
      </button>
      <span className="mr-auto text-sm font-medium">{ids.length} selected</span>
      <CategoryPicker
        up
        label="Move to"
        documentIds={ids}
        onPick={(c) =>
          c.id === "__created__"
            ? (onClear(), onDone())
            : bulk("categorize", { category_id: c.id }, `Moved ${ids.length} to “${c.name}”`)
        }
      />
      <AddToProject up documentIds={ids} label="Project" onDone={() => { onClear(); onDone(); }} />
      <button onClick={() => bulk("favorite", {}, "Added to favorites")} aria-label="Favorite" className="rounded-lg border border-line p-2 hover:bg-white">
        <Star className="h-4 w-4" />
      </button>
      <button
        onClick={() => confirm(`Delete ${ids.length} item${ids.length > 1 ? "s" : ""} permanently?`) && bulk("delete", {}, `Deleted ${ids.length}`)}
        aria-label="Delete"
        className="rounded-lg border border-line p-2 text-muted hover:text-accent"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}
