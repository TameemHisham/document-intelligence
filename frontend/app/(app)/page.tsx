"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCheck, Sparkles, UploadCloud } from "lucide-react";
import { api, json, type Doc } from "@/lib/api";
import { isBusy, useApi } from "@/lib/hooks";
import { useSelection } from "@/lib/selection";
import { PhotoGrid } from "@/components/PhotoGrid";
import { SelectionBar } from "@/components/SelectionBar";
import { useToast } from "@/components/Toast";

const TABS = [
  { id: "", label: "All", query: "" },
  { id: "photo", label: "Photos", query: "kind=photo" },
  { id: "document", label: "Documents", query: "kind=document" },
  { id: "favorites", label: "Favorites", query: "favorite=true" },
  { id: "unfiled", label: "Needs category", query: "uncategorized=true" },
];

export default function LibraryPage() {
  const router = useRouter();
  const toast = useToast();
  const params = useSearchParams();
  const tab = params.get("favorite") === "1" ? "favorites" : (params.get("tab") ?? "");
  const query = TABS.find((t) => t.id === tab)?.query ?? "";
  const { data: docs, error, setData, reload } = useApi<Doc[]>(`/documents?limit=500${query ? `&${query}` : ""}`, {
    shouldPoll: (d) => d.some((x) => isBusy(x.status)),
  });
  const { data: unfiled, reload: reloadUnfiled } = useApi<Doc[]>("/documents?uncategorized=true&limit=500");
  const sel = useSelection();

  const replace = (d: Doc) => {
    setData((ds) => (tab === "unfiled" && d.category ? ds?.filter((x) => x.id !== d.id) : ds?.map((x) => (x.id === d.id ? d : x))) ?? null);
    reloadUnfiled();
  };
  const refresh = () => {
    reload();
    reloadUnfiled();
  };

  const acceptAll = async () => {
    const ids = (docs ?? []).filter((d) => d.suggestions.length).map((d) => d.id);
    if (!ids.length) return;
    await api("/documents/bulk", json("POST", { document_ids: ids, action: "accept_suggestions" }));
    toast(`Filed ${ids.length} item${ids.length > 1 ? "s" : ""} using suggestions`);
    refresh();
  };

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow mb-1 hidden md:block">Personal Archive</p>
          <h1 className="font-serif text-3xl md:text-4xl">Your Library</h1>
        </div>
        <Link href="/upload" className="hidden items-center gap-2 rounded-lg bg-ink px-4 py-2 text-sm text-white md:flex">
          <UploadCloud className="h-4 w-4" /> Upload
        </Link>
      </div>

      <div className="-mx-4 mb-5 flex gap-2 overflow-x-auto px-4 pb-1 md:mx-0 md:px-0">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => {
              sel.clear();
              router.push(t.id ? `/?tab=${t.id}` : "/");
            }}
            className={`shrink-0 rounded-full border px-3 py-1.5 text-xs ${
              tab === t.id ? "border-ink bg-ink text-white" : "border-line bg-card text-muted hover:text-ink"
            }`}
          >
            {t.label}
            {t.id === "unfiled" && !!unfiled?.length && (
              <span className={`ml-1.5 rounded-full px-1.5 font-mono text-[10px] ${tab === t.id ? "bg-white/20" : "bg-accent text-white"}`}>
                {unfiled.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {tab === "" && !!unfiled?.length && (
        <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-card p-3 text-sm">
          <Sparkles className="h-4 w-4 text-accent" />
          <span className="flex-1">
            {unfiled.length} item{unfiled.length > 1 ? "s" : ""} need{unfiled.length === 1 ? "s" : ""} a category. The AI has suggestions ready.
          </span>
          <Link href="/?tab=unfiled" className="rounded-lg bg-ink px-3 py-1.5 text-xs text-white">Review</Link>
        </div>
      )}

      {tab === "unfiled" && !!docs?.length && (
        <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-card p-3 text-sm">
          <span className="flex-1 text-muted">Tap a suggestion to file an item, or accept the top suggestion for all of them.</span>
          <button onClick={acceptAll} className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-xs text-white">
            <CheckCheck className="h-3.5 w-3.5" /> Accept all suggestions
          </button>
        </div>
      )}

      {error && <p className="text-sm text-accent">{error}</p>}
      {!docs && !error && <GridSkeleton />}

      {docs && docs.length === 0 && (
        <div className="mx-auto mt-10 max-w-md rounded-xl border border-dashed border-line bg-card p-10 text-center">
          <h2 className="font-serif text-2xl">{tab === "unfiled" ? "All sorted" : tab ? "Nothing here yet" : "Your library is empty"}</h2>
          <p className="mt-2 text-sm text-muted">
            {tab === "unfiled" ? "Every item has a category." : "Add photos, receipts, notes or manuals. They're organized automatically."}
          </p>
          {tab !== "unfiled" && (
            <Link href="/upload" className="mt-5 inline-flex items-center gap-2 rounded-lg bg-ink px-4 py-2 text-sm text-white">
              <UploadCloud className="h-4 w-4" /> Upload
            </Link>
          )}
        </div>
      )}

      {docs && docs.length > 0 && (
        <>
          <div className="mb-3 flex items-center justify-between text-xs text-muted">
            <span>{docs.length} item{docs.length > 1 ? "s" : ""}</span>
            <button
              onClick={() => (sel.selected.size ? sel.clear() : sel.selectAll(docs.map((d) => d.id)))}
              className="hover:text-ink"
            >
              {sel.selected.size ? "Clear selection" : "Select all"}
            </button>
          </div>
          <PhotoGrid docs={docs} selected={sel.selected} onToggle={sel.toggle} onChange={replace} groupByMonth={tab !== "unfiled"} />
        </>
      )}

      <SelectionBar ids={sel.ids} onClear={sel.clear} onDone={refresh} />
    </div>
  );
}

function GridSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3 lg:grid-cols-4 xl:grid-cols-5">
      {Array.from({ length: 10 }, (_, i) => (
        <div key={i} className="aspect-square animate-pulse rounded-xl bg-line/60" />
      ))}
    </div>
  );
}
