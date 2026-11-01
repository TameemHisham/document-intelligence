"use client";

import Link from "next/link";
import { useState } from "react";
import { FolderKanban, Plus } from "lucide-react";
import { api, json, type Project } from "@/lib/api";
import { useApi } from "@/lib/hooks";

export default function ProjectsPage() {
  const { data: projects, reload } = useApi<Project[]>("/projects");
  const [name, setName] = useState("");

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    await api("/projects", json("POST", { name }));
    setName("");
    reload();
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow mb-1">Collections to question</p>
          <h1 className="font-serif text-3xl md:text-4xl">Projects</h1>
        </div>
        <form onSubmit={create} className="flex gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="New project"
            className="rounded-lg border border-line bg-card px-3 py-2 text-xs outline-none focus:border-ink"
          />
          <button className="flex items-center gap-1.5 rounded-lg bg-ink px-3 py-2 text-xs text-white">
            <Plus className="h-3.5 w-3.5" /> Create
          </button>
        </form>
      </div>
      <p className="mb-6 text-sm text-muted">
        Search your library, add the results to a project, then ask questions across just those sources.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {projects?.map((p) => (
          <Link key={p.id} href={`/projects/${p.id}`} className="flex items-center gap-4 rounded-lg border border-line bg-card p-4 hover:shadow-md">
            <FolderKanban className="h-6 w-6 text-ink" />
            <div>
              <p className="font-serif text-lg">{p.name}</p>
              <p className="font-mono text-[10px] uppercase text-muted">{p.document_count} sources</p>
            </div>
          </Link>
        ))}
      </div>
      {projects?.length === 0 && <p className="text-sm text-muted">No projects yet.</p>}
    </div>
  );
}
