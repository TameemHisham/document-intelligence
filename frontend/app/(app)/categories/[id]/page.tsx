"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, Pencil } from "lucide-react";
import type { Category, Doc } from "@/lib/api";
import { isBusy, useApi } from "@/lib/hooks";
import { useSelection } from "@/lib/selection";
import { PhotoGrid } from "@/components/PhotoGrid";
import { SelectionBar } from "@/components/SelectionBar";
import { CategoryDialog } from "@/components/CategoryDialog";

export default function CategoryPage() {
  const { id } = useParams<{ id: string }>();
  const { data: cats, reload: reloadCats } = useApi<Category[]>("/categories");
  const { data: docs, reload } = useApi<Doc[]>(`/documents?category_id=${id}&limit=500`, {
    shouldPoll: (d) => d.some((x) => isBusy(x.status)),
  });
  const [editing, setEditing] = useState(false);
  const sel = useSelection();
  const cat = cats?.find((c) => c.id === id);

  if (cats && !cat) return <p className="text-sm text-muted">Category not found. <Link href="/categories" className="underline">Back</Link></p>;

  return (
    <div className="mx-auto max-w-6xl">
      <Link href="/categories" className="mb-4 inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink">
        <ArrowLeft className="h-3.5 w-3.5" /> Categories
      </Link>
      {cat && (
        <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="flex items-center gap-2 font-serif text-3xl md:text-4xl">
              <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: cat.color }} />
              <span className="truncate">{cat.name}</span>
            </h1>
            <p className="mt-1 text-sm text-muted">
              {cat.count} item{cat.count === 1 ? "" : "s"}
              {cat.source === "ai" && " · created by AI"}
              {cat.description && ` · ${cat.description}`}
            </p>
          </div>
          <button onClick={() => setEditing(true)} className="flex items-center gap-1.5 rounded-lg border border-line bg-card px-3 py-2 text-xs">
            <Pencil className="h-3.5 w-3.5" /> Edit
          </button>
        </div>
      )}

      {docs?.length === 0 && (
        <p className="rounded-xl border border-dashed border-line p-10 text-center text-sm text-muted">
          Nothing here yet. Select items in your <Link href="/" className="underline">library</Link> and choose “Move to”.
        </p>
      )}
      {docs && docs.length > 0 && <PhotoGrid docs={docs} selected={sel.selected} onToggle={sel.toggle} />}

      <SelectionBar ids={sel.ids} onClear={sel.clear} onDone={() => { reload(); reloadCats(); }} />
      {editing && cat && <CategoryDialog open category={cat} onClose={() => setEditing(false)} onSaved={reloadCats} />}
    </div>
  );
}
