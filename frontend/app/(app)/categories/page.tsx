"use client";

/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { useState } from "react";
import { GitMerge, MoreHorizontal, Plus, Sparkles, X } from "lucide-react";
import { api, fileSrc, json, type Category, type CategorySuggestions } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Collage } from "@/components/Collage";
import { CategoryDialog } from "@/components/CategoryDialog";
import { useToast } from "@/components/Toast";

const DISMISSED_KEY = "di_dismissed_merges";

export default function CategoriesPage() {
  const toast = useToast();
  const { data: cats, reload } = useApi<Category[]>("/categories");
  const { data: sugg, reload: reloadSugg } = useApi<CategorySuggestions>("/categories/suggestions");
  const [creating, setCreating] = useState<{ name?: string; ids?: string[] } | null>(null);
  const [editing, setEditing] = useState<Category | null>(null);
  const [dismissed, setDismissed] = useState<string[]>(() =>
    typeof window === "undefined" ? [] : JSON.parse(localStorage.getItem(DISMISSED_KEY) ?? "[]"),
  );

  const refresh = () => {
    reload();
    reloadSugg();
  };
  const dismiss = (key: string) => {
    const next = [...dismissed, key];
    setDismissed(next);
    localStorage.setItem(DISMISSED_KEY, JSON.stringify(next));
  };
  const merge = async (sourceId: string, target: Category, sourceName: string) => {
    await api(`/categories/${sourceId}/merge`, json("POST", { into_id: target.id }));
    toast(`Merged “${sourceName}” into “${target.name}”`);
    refresh();
  };
  const remove = async (c: Category) => {
    if (!confirm(`Delete “${c.name}”? Its ${c.count} item${c.count === 1 ? "" : "s"} will need a new category.`)) return;
    await api(`/categories/${c.id}`, { method: "DELETE" });
    toast(`Deleted “${c.name}”`);
    refresh();
  };

  const merges = sugg?.merges.filter((m) => !dismissed.includes(`${m.source.id}:${m.target.id}`)) ?? [];
  const proposed = sugg?.proposed.filter((p) => !dismissed.includes(`new:${p.name.toLowerCase()}`)) ?? [];

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow mb-1">Organized for you</p>
          <h1 className="font-serif text-3xl md:text-4xl">Categories</h1>
        </div>
        <button onClick={() => setCreating({})} className="flex items-center gap-1.5 rounded-lg bg-ink px-4 py-2 text-sm text-white">
          <Plus className="h-4 w-4" /> New category
        </button>
      </div>

      {(merges.length > 0 || proposed.length > 0 || !!sugg?.unfiled) && (
        <section className="mb-8 space-y-3">
          <h2 className="eyebrow flex items-center gap-1.5">
            <Sparkles className="h-3 w-3 text-accent" /> Suggestions
          </h2>

          {proposed.map((p) => (
            <div key={p.name} className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-card p-3">
              <div className="flex -space-x-2">
                {p.documents.slice(0, 3).map((d) =>
                  d.mime.startsWith("image/") ? (
                    <img key={d.id} src={fileSrc(d)} alt="" className="h-10 w-10 rounded-lg border-2 border-card object-cover" />
                  ) : (
                    <div key={d.id} className="h-10 w-10 rounded-lg border-2 border-card bg-line" />
                  ),
                )}
              </div>
              <p className="min-w-0 flex-1 text-sm">
                New category <b>“{p.name}”</b> for {p.documents.length} item{p.documents.length > 1 ? "s" : ""}
                <span className="block text-xs text-muted">{p.documents.map((d) => d.title).slice(0, 3).join(", ")}</span>
              </p>
              <button onClick={() => dismiss(`new:${p.name.toLowerCase()}`)} className="text-xs text-muted hover:text-ink">Not now</button>
              <button
                onClick={() => setCreating({ name: p.name, ids: p.documents.map((d) => d.id) })}
                className="rounded-lg bg-ink px-3 py-1.5 text-xs text-white"
              >
                Create
              </button>
            </div>
          ))}

          {merges.map((m) => (
            <div key={`${m.source.id}:${m.target.id}`} className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-card p-3">
              <GitMerge className="h-5 w-5 text-ink" />
              <p className="min-w-0 flex-1 text-sm">
                <b>“{m.source.name}”</b> looks like <b>“{m.target.name}”</b>
                <span className="block text-xs text-muted">{m.reason} · merge to keep things tidy</span>
              </p>
              <button onClick={() => dismiss(`${m.source.id}:${m.target.id}`)} aria-label="Dismiss" className="text-muted hover:text-ink">
                <X className="h-4 w-4" />
              </button>
              <button onClick={() => merge(m.source.id, m.target, m.source.name)} className="rounded-lg bg-ink px-3 py-1.5 text-xs text-white">
                Merge
              </button>
            </div>
          ))}

          {!!sugg?.unfiled && (
            <Link href="/?tab=unfiled" className="flex items-center gap-3 rounded-xl border border-dashed border-line p-3 text-sm text-muted hover:text-ink">
              {sugg.unfiled} item{sugg.unfiled > 1 ? "s" : ""} still need a category →
            </Link>
          )}
        </section>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {cats?.map((c) => (
          <div key={c.id} className="group relative overflow-hidden rounded-xl border border-line bg-card transition hover:shadow-md">
            <Link href={`/categories/${c.id}`} className="block">
              <Collage category={c} className="aspect-[4/3] w-full" />
              <div className="p-3">
                <p className="flex items-center gap-1.5 truncate font-serif text-lg leading-tight">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: c.color }} />
                  <span className="truncate">{c.name}</span>
                </p>
                <p className="mt-0.5 truncate text-xs text-muted">
                  {c.count} item{c.count === 1 ? "" : "s"}
                  {c.source === "ai" && " · created by AI"}
                  {c.description && ` · ${c.description}`}
                </p>
              </div>
            </Link>
            <CardMenu onEdit={() => setEditing(c)} onDelete={() => remove(c)} />
          </div>
        ))}
        <button
          onClick={() => setCreating({})}
          className="grid aspect-[4/3] place-items-center rounded-xl border-2 border-dashed border-line text-sm text-muted hover:border-ink hover:text-ink sm:aspect-auto sm:min-h-48"
        >
          <span className="flex flex-col items-center gap-1">
            <Plus className="h-5 w-5" /> New category
          </span>
        </button>
      </div>

      {creating && (
        <CategoryDialog
          open
          initialName={creating.name}
          documentIds={creating.ids}
          onClose={() => setCreating(null)}
          onSaved={refresh}
        />
      )}
      {editing && <CategoryDialog open category={editing} onClose={() => setEditing(null)} onSaved={refresh} />}
    </div>
  );
}

function CardMenu({ onEdit, onDelete }: { onEdit: () => void; onDelete: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="absolute right-2 top-2">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Category options"
        className="rounded-full bg-white/90 p-1 text-ink shadow sm:opacity-0 sm:group-hover:opacity-100"
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-32 rounded-lg border border-line bg-card p-1 text-xs shadow-lg" onMouseLeave={() => setOpen(false)}>
          <button onClick={() => { setOpen(false); onEdit(); }} className="block w-full rounded px-2 py-1.5 text-left hover:bg-background">Edit</button>
          <button onClick={() => { setOpen(false); onDelete(); }} className="block w-full rounded px-2 py-1.5 text-left text-accent hover:bg-background">Delete</button>
        </div>
      )}
    </div>
  );
}
