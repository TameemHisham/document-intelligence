"use client";

import { useState } from "react";
import { api, COLORS, json, type Category } from "@/lib/api";
import { Dialog } from "./Dialog";
import { useToast } from "./Toast";

/** Create (optionally filing documents into it) or edit a category. */
export function CategoryDialog({
  open,
  onClose,
  onSaved,
  category,
  documentIds = [],
  initialName = "",
}: {
  open: boolean;
  onClose: () => void;
  onSaved: (c: Category) => void;
  category?: Category;
  documentIds?: string[];
  initialName?: string;
}) {
  const toast = useToast();
  const [name, setName] = useState(category?.name ?? initialName);
  const [description, setDescription] = useState(category?.description ?? "");
  const [color, setColor] = useState(() => category?.color ?? COLORS[(initialName.length + Date.now()) % COLORS.length]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const body = { name, description, color };
      const saved = category
        ? await api<Category>(`/categories/${category.id}`, json("PATCH", body))
        : await api<Category>("/categories", json("POST", { ...body, document_ids: documentIds }));
      toast(category ? "Category updated" : `Created “${saved.name}”${documentIds.length ? ` with ${documentIds.length} item${documentIds.length > 1 ? "s" : ""}` : ""}`);
      onSaved(saved);
      onClose();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title={category ? "Edit category" : "New category"}>
      <form onSubmit={save} className="space-y-4 text-sm">
        <label className="block">
          <span className="eyebrow">Name</span>
          <input
            autoFocus
            required
            maxLength={40}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Gym progress"
            className="mt-1 w-full rounded-lg border border-line bg-background px-3 py-2 outline-none focus:border-ink"
          />
        </label>
        <label className="block">
          <span className="eyebrow">Description (optional)</span>
          <input
            maxLength={200}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What belongs here? Helps the AI sort new uploads."
            className="mt-1 w-full rounded-lg border border-line bg-background px-3 py-2 outline-none focus:border-ink"
          />
        </label>
        <div>
          <span className="eyebrow">Color</span>
          <div className="mt-2 flex flex-wrap gap-2">
            {COLORS.map((c) => (
              <button
                type="button"
                key={c}
                onClick={() => setColor(c)}
                aria-label={`Color ${c}`}
                className={`h-8 w-8 rounded-full ring-offset-2 ${color === c ? "ring-2 ring-ink" : ""}`}
                style={{ background: c }}
              />
            ))}
          </div>
        </div>
        {documentIds.length > 0 && !category && (
          <p className="text-xs text-muted">{documentIds.length} selected item{documentIds.length > 1 ? "s" : ""} will be filed here.</p>
        )}
        {err && <p className="text-xs text-accent">{err}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="rounded-lg border border-line px-4 py-2">Cancel</button>
          <button disabled={busy || !name.trim()} className="rounded-lg bg-ink px-4 py-2 text-white disabled:opacity-50">
            {category ? "Save" : "Create"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
