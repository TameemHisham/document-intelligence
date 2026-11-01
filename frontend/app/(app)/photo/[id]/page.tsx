"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Check, RefreshCw, Star, Trash2 } from "lucide-react";
import { api, json, type DocDetail } from "@/lib/api";
import { isBusy, useApi } from "@/lib/hooks";
import { Thumb } from "@/components/Thumb";
import { AddToProject } from "@/components/AddToProject";
import { AskPanel } from "@/components/AskPanel";
import { CategoryPicker } from "@/components/CategoryPicker";
import { SuggestionChips } from "@/components/Suggestions";

const SUGGESTIONS: Record<string, string> = {
  expiry_date: "When does this expire?",
  total: "How much did I pay?",
  serial: "What's the serial number?",
  place: "Where was this?",
};

export default function DocumentPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: doc, error, setData, reload } = useApi<DocDetail>(`/documents/${id}`, { shouldPoll: (d) => isBusy(d.status) });

  if (error) return <p className="text-sm text-accent">{error}</p>;
  if (!doc) return <p className="eyebrow">Loading…</p>;

  const patch = async (body: object) => setData(await api<DocDetail>(`/documents/${id}`, json("PATCH", body)));
  const confirmCat = async () => setData(await api<DocDetail>(`/documents/${id}/confirm-category`, { method: "POST" }));
  const reprocess = async () => {
    await api(`/documents/${id}/reprocess`, { method: "POST" });
    reload();
  };
  const remove = async () => {
    if (!confirm("Delete this item permanently?")) return;
    await api(`/documents/${id}`, { method: "DELETE" });
    router.push("/");
  };

  const suggestions = [
    ...doc.fields.map((f) => SUGGESTIONS[f.field]).filter(Boolean),
    doc.kind === "photo" ? "Describe what's in this photo" : "Summarize this document",
  ].slice(0, 3);

  return (
    <div className="mx-auto max-w-5xl">
      <Link href="/" className="mb-4 inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink">
        <ArrowLeft className="h-3.5 w-3.5" /> Library
      </Link>

      <div className="grid gap-6 md:grid-cols-[1fr_1.1fr]">
        <div>
          <Thumb doc={doc} className="aspect-[4/3] w-full rounded-xl border border-line [&_img]:object-contain" />
          {doc.error && <p className="mt-2 text-xs text-accent">{doc.error}</p>}
          <p className="mt-2 font-mono text-[10px] uppercase text-muted">
            {doc.taken_at ? `Taken ${new Date(doc.taken_at).toLocaleDateString()}` : `Added ${new Date(doc.created_at).toLocaleDateString()}`}
          </p>

          <div className="mt-4 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="font-serif text-3xl leading-tight">{doc.title}</h1>
              <p className="mt-1 text-sm text-muted">{doc.summary}</p>
            </div>
            <div className="flex shrink-0 gap-1.5">
              <button onClick={() => patch({ favorite: !doc.favorite })} aria-label="Favorite" className="rounded-lg border border-line bg-card p-2">
                <Star className={`h-4 w-4 ${doc.favorite ? "fill-accent text-accent" : "text-muted"}`} />
              </button>
              <AddToProject documentIds={[doc.id]} />
            </div>
          </div>

          <h2 className="eyebrow mb-2 mt-6">Category</h2>
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-card p-3 text-sm">
            {doc.category ? (
              <>
                <span className="flex items-center gap-1.5 font-medium">
                  <span className="h-2 w-2 rounded-full" style={{ background: doc.category.color }} />
                  {doc.category.name}
                </span>
                <span className="font-mono text-[10px] uppercase text-muted">
                  {doc.category_confirmed ? "confirmed" : `${doc.category_method} · ${Math.round(doc.category_confidence * 100)}%`}
                </span>
                {!doc.category_confirmed && (
                  <button onClick={confirmCat} className="flex items-center gap-1 rounded bg-ink px-2 py-1 text-xs text-white">
                    <Check className="h-3 w-3" /> Looks right
                  </button>
                )}
              </>
            ) : (
              <SuggestionChips doc={doc} onFiled={() => reload()} />
            )}
            <CategoryPicker
              className="ml-auto"
              label={doc.category ? "Change" : "Choose…"}
              documentIds={[doc.id]}
              onPick={(c) => (c.id === "__created__" ? reload() : patch({ category_id: c.id }))}
            />
          </div>

          {doc.fields.length > 0 && (
            <>
              <h2 className="eyebrow mb-2 mt-6">Extracted fields</h2>
              <dl className="divide-y divide-line rounded-lg border border-line bg-card text-sm">
                {doc.fields.map((f) => (
                  <div key={f.field} className="flex justify-between gap-4 px-3 py-2">
                    <dt className="text-muted">{f.label}</dt>
                    <dd className="text-right font-medium">{f.value}</dd>
                  </div>
                ))}
              </dl>
            </>
          )}

          {doc.caption && (
            <>
              <h2 className="eyebrow mb-2 mt-6">Visual description</h2>
              <p className="rounded-lg border border-line bg-card p-3 text-sm text-muted">{doc.caption}</p>
            </>
          )}

          {doc.ocr_text && (
            <details className="mt-6">
              <summary className="eyebrow cursor-pointer">Recognized text</summary>
              <p className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg border border-line bg-card p-3 font-mono text-[11px] leading-relaxed text-muted">
                {doc.ocr_text}
              </p>
            </details>
          )}

          <div className="mt-6 flex gap-2 text-xs">
            <button onClick={reprocess} className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-muted hover:text-ink">
              <RefreshCw className="h-3.5 w-3.5" /> Re-process
            </button>
            <button onClick={remove} className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-muted hover:text-accent">
              <Trash2 className="h-3.5 w-3.5" /> Delete
            </button>
          </div>
        </div>

        {doc.status === "ready" ? (
          <AskPanel scope={{ document_ids: [doc.id] }} suggestions={suggestions} placeholder="e.g. When does this expire?" />
        ) : (
          <p className="eyebrow">Processing… questions open once it&apos;s ready.</p>
        )}
      </div>
    </div>
  );
}
