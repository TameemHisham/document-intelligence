"use client";

import { useState } from "react";
import { Check, FolderPlus, Plus } from "lucide-react";
import { api, json, type Project } from "@/lib/api";
import { useToast } from "./Toast";

/** Dropdown: add one or more documents to an existing or new project. */
export function AddToProject({
  documentIds,
  label = "Add to project",
  onDone,
  up = false,
}: {
  documentIds: string[];
  label?: string;
  onDone?: () => void;
  up?: boolean;
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [name, setName] = useState("");
  const [added, setAdded] = useState<string | null>(null);

  const toggle = async () => {
    setOpen((o) => !o);
    if (!projects) setProjects(await api<Project[]>("/projects"));
  };

  const add = async (projectId: string) => {
    await api(`/projects/${projectId}/documents`, json("POST", { document_ids: documentIds }));
    setAdded(projectId);
    toast(`Added ${documentIds.length} to “${projects?.find((p) => p.id === projectId)?.name ?? "project"}”`);
    onDone?.();
    setTimeout(() => setOpen(false), 600);
  };

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    const p = await api<Project>("/projects", json("POST", { name }));
    setProjects((ps) => [p, ...(ps ?? [])]);
    setName("");
    await add(p.id);
  };

  return (
    <div className="relative">
      <button
        onClick={toggle}
        disabled={!documentIds.length}
        className="flex items-center gap-1.5 rounded-lg border border-line bg-card px-3 py-2 text-xs hover:bg-white disabled:opacity-40"
      >
        <FolderPlus className="h-3.5 w-3.5" /> {label}
      </button>
      {open && (
        <div className={`absolute right-0 z-30 w-64 rounded-lg border border-line bg-card p-2 shadow-lg ${up ? "bottom-full mb-1" : "mt-1"}`}>
          <form onSubmit={create} className="mb-2 flex gap-1">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="New project name"
              className="min-w-0 flex-1 rounded border border-line px-2 py-1 text-xs outline-none focus:border-ink"
            />
            <button aria-label="Create project" className="grid w-7 place-items-center rounded bg-ink text-white">
              <Plus className="h-3.5 w-3.5" />
            </button>
          </form>
          <div className="max-h-56 overflow-y-auto">
            {projects === null && <p className="p-2 text-xs text-muted">Loading…</p>}
            {projects?.length === 0 && <p className="p-2 text-xs text-muted">No projects yet.</p>}
            {projects?.map((p) => (
              <button key={p.id} onClick={() => add(p.id)} className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs hover:bg-background">
                <span className="truncate">{p.name}</span>
                {added === p.id ? <Check className="h-3.5 w-3.5 text-ink" /> : <span className="font-mono text-[10px] text-muted">{p.document_count}</span>}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
