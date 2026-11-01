"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, CheckCheck, CheckCircle2, FolderOpen, Loader2, TriangleAlert, UploadCloud } from "lucide-react";
import { api, ApiError, json, type Doc } from "@/lib/api";
import { isBusy } from "@/lib/hooks";
import { Thumb } from "@/components/Thumb";
import { SuggestionChips } from "@/components/Suggestions";
import { useToast } from "@/components/Toast";

const ACCEPT = ["image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"];
const MAX_MB = 20;
const BATCH_FILES = 5; // per request
const BATCH_BYTES = 25 * 1024 * 1024; // stay under Cloud Run's 32 MB request limit

type Item = { key: string; file: File; state: "queued" | "uploading" | "done" | "error"; error?: string; doc?: Doc };

function batches(items: Item[]): Item[][] {
  const out: Item[][] = [];
  let cur: Item[] = [];
  let bytes = 0;
  for (const it of items) {
    if (cur.length && (cur.length >= BATCH_FILES || bytes + it.file.size > BATCH_BYTES)) {
      out.push(cur);
      cur = [];
      bytes = 0;
    }
    cur.push(it);
    bytes += it.file.size;
  }
  if (cur.length) out.push(cur);
  return out;
}

export default function UploadPage() {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [running, setRunning] = useState(false);
  const [dragging, setDragging] = useState(false);

  const patch = (keys: string[], p: Partial<Item> | ((it: Item) => Partial<Item>)) =>
    setItems((list) => list.map((it) => (keys.includes(it.key) ? { ...it, ...(typeof p === "function" ? p(it) : p) } : it)));

  const send = async (group: Item[]): Promise<void> => {
    const keys = group.map((g) => g.key);
    patch(keys, { state: "uploading" });
    const form = new FormData();
    group.forEach((g) => form.append("files", g.file));
    try {
      const docs = await api<Doc[]>("/documents", { method: "POST", body: form });
      setItems((list) => list.map((it) => {
        const i = keys.indexOf(it.key);
        return i >= 0 ? { ...it, state: "done", doc: docs[i] } : it;
      }));
    } catch (e) {
      const err = e as ApiError;
      if ((err.status === 413 || err.status === 415) && group.length > 1) {
        for (const g of group) await send([g]); // isolate the bad file; upload the rest
        return;
      }
      if (err.status === 429 && err.message.startsWith("Too many requests")) {
        const wait = Number(err.message.match(/(\d+)s/)?.[1] ?? 10);
        await new Promise((r) => setTimeout(r, wait * 1000));
        return send(group);
      }
      patch(keys, { state: "error", error: err.message });
    }
  };

  const start = useCallback(async (files: File[]) => {
    const fresh: Item[] = files.map((f) => ({ key: `${f.name}-${f.size}-${f.lastModified}-${Math.random()}`, file: f, state: "queued" }));
    for (const it of fresh) {
      if (!ACCEPT.includes(it.file.type)) Object.assign(it, { state: "error", error: "Not an image or PDF" });
      else if (it.file.size > MAX_MB * 1024 * 1024) Object.assign(it, { state: "error", error: `Larger than ${MAX_MB} MB` });
    }
    setItems((list) => [...fresh, ...list]);
    setRunning(true);
    for (const group of batches(fresh.filter((f) => f.state === "queued"))) await send(group);
    setRunning(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll processing status for everything uploaded in this session (one request for all).
  const inFlight = items.some((it) => it.doc && isBusy(it.doc.status));
  useEffect(() => {
    if (!inFlight) return;
    const t = setTimeout(async () => {
      const latest = await api<Doc[]>("/documents?limit=500");
      const byId = new Map(latest.map((d) => [d.id, d]));
      setItems((list) => list.map((it) => (it.doc && byId.has(it.doc.id) ? { ...it, doc: byId.get(it.doc.id) } : it)));
    }, 2000);
    return () => clearTimeout(t);
  }, [items, inFlight]);

  // Drop anywhere on the page.
  useEffect(() => {
    const over = (e: DragEvent) => {
      e.preventDefault();
      setDragging(true);
    };
    const leave = (e: DragEvent) => !e.relatedTarget && setDragging(false);
    const drop = (e: DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (e.dataTransfer?.files.length) start(Array.from(e.dataTransfer.files));
    };
    window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
  }, [start]);

  const uploaded = items.filter((i) => i.state === "done").length;
  const processed = items.filter((i) => i.doc?.status === "ready" || i.doc?.status === "failed").length;
  const failed = items.filter((i) => i.state === "error").length;
  const total = items.length;
  const unfiled = items.filter((i) => i.doc?.status === "ready" && !i.doc.category && i.doc.suggestions.length).map((i) => i.doc!.id);
  const pct = total ? Math.round(((uploaded + processed) / (2 * (total - failed || 1))) * 100) : 0;

  const acceptAll = async () => {
    await api("/documents/bulk", json("POST", { document_ids: unfiled, action: "accept_suggestions" }));
    const latest = await api<Doc[]>("/documents?limit=500");
    const byId = new Map(latest.map((d) => [d.id, d]));
    setItems((list) => list.map((it) => (it.doc && byId.has(it.doc.id) ? { ...it, doc: byId.get(it.doc.id) } : it)));
    toast(`Filed ${unfiled.length} item${unfiled.length > 1 ? "s" : ""}`);
  };

  return (
    <div className="mx-auto max-w-3xl">
      <p className="eyebrow mb-1">Add to library</p>
      <h1 className="mb-6 font-serif text-3xl md:text-4xl">Upload</h1>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT.join(",")}
        className="hidden"
        onChange={(e) => {
          if (e.target.files?.length) start(Array.from(e.target.files));
          e.target.value = "";
        }}
      />
      <div
        className={`flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed p-8 text-center transition sm:p-12 ${
          dragging ? "border-ink bg-white" : "border-line bg-card"
        }`}
      >
        <UploadCloud className="h-9 w-9 text-muted" />
        <p className="text-sm">
          <span className="hidden sm:inline">Drop photos and documents anywhere on this page, or</span>
          <span className="sm:hidden">Add photos and documents</span>
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          <button onClick={() => inputRef.current?.click()} className="flex items-center gap-2 rounded-lg bg-ink px-4 py-2 text-sm text-white">
            <FolderOpen className="h-4 w-4" /> Choose files
          </button>
          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-line px-4 py-2 text-sm sm:hidden">
            <Camera className="h-4 w-4" /> Camera
            <input type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => e.target.files?.length && start(Array.from(e.target.files))} />
          </label>
        </div>
        <p className="text-xs text-muted">Select as many as you like · JPG, PNG, WebP, GIF, PDF · up to {MAX_MB} MB each</p>
      </div>

      {total > 0 && (
        <div className="mt-6 rounded-xl border border-line bg-card p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="flex items-center gap-2">
              {running || inFlight ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4 text-ink" />}
              {uploaded}/{total - failed} uploaded · {processed} processed{failed ? ` · ${failed} failed` : ""}
            </span>
            {!running && !inFlight && (
              <div className="flex gap-2">
                {unfiled.length > 0 && (
                  <button onClick={acceptAll} className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs">
                    <CheckCheck className="h-3.5 w-3.5" /> Accept {unfiled.length} suggestion{unfiled.length > 1 ? "s" : ""}
                  </button>
                )}
                <Link href="/" className="rounded-lg bg-ink px-3 py-1.5 text-xs text-white">View library</Link>
              </div>
            )}
          </div>
          <div className="h-1.5 overflow-hidden rounded bg-line">
            <div className="h-full bg-ink transition-all" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      {total > 0 && (
        <ul className="mt-4 divide-y divide-line rounded-xl border border-line bg-card">
          {items.map((it) => (
            <li key={it.key} className="flex items-center gap-3 p-3">
              {it.doc ? (
                <Thumb doc={it.doc} className="h-14 w-14 shrink-0 rounded-md" />
              ) : (
                <div className="grid h-14 w-14 shrink-0 place-items-center rounded-md bg-line/60">
                  {it.state === "error" ? <TriangleAlert className="h-4 w-4 text-accent" /> : <Loader2 className="h-4 w-4 animate-spin text-muted" />}
                </div>
              )}
              <div className="min-w-0 flex-1 text-sm">
                {it.doc?.status === "ready" ? (
                  <>
                    <Link href={`/photo/${it.doc.id}`} className="block truncate font-medium hover:underline">{it.doc.title}</Link>
                    {it.doc.category ? (
                      <span className="flex items-center gap-1.5 text-xs text-muted">
                        <span className="h-1.5 w-1.5 rounded-full" style={{ background: it.doc.category.color }} />
                        {it.doc.category.name}
                      </span>
                    ) : (
                      <SuggestionChips doc={it.doc} onFiled={(d) => patch([it.key], { doc: d })} />
                    )}
                  </>
                ) : (
                  <>
                    <p className="truncate">{it.file.name}</p>
                    <p className={`text-xs ${it.state === "error" || it.doc?.status === "failed" ? "text-accent" : "text-muted"}`}>
                      {it.state === "error"
                        ? it.error
                        : it.doc?.status === "failed"
                          ? it.doc.error || "Processing failed"
                          : it.state === "done"
                            ? "Reading, describing and sorting…"
                            : it.state === "uploading"
                              ? "Uploading…"
                              : "Waiting…"}
                    </p>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
