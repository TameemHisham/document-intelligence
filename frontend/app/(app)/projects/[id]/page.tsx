"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Trash2, X } from "lucide-react";
import { api, type Project } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { WideCard } from "@/components/ItemCard";
import { AskPanel } from "@/components/AskPanel";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: project, error, setData } = useApi<Project>(`/projects/${id}`);

  if (error) return <p className="text-sm text-accent">{error}</p>;
  if (!project) return <p className="eyebrow">Loading…</p>;

  const removeDoc = async (docId: string) => setData(await api<Project>(`/projects/${id}/documents/${docId}`, { method: "DELETE" }));
  const removeProject = async () => {
    if (!confirm(`Delete project “${project.name}”? The items stay in your library.`)) return;
    await api(`/projects/${id}`, { method: "DELETE" });
    router.push("/projects");
  };

  return (
    <div className="mx-auto max-w-6xl">
      <Link href="/projects" className="mb-4 inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink">
        <ArrowLeft className="h-3.5 w-3.5" /> Projects
      </Link>
      <div className="mb-6 flex items-end justify-between gap-3">
        <div>
          <p className="eyebrow mb-1">{project.document_count} sources</p>
          <h1 className="font-serif text-3xl md:text-4xl">{project.name}</h1>
        </div>
        <button onClick={removeProject} className="flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-xs text-muted hover:text-accent">
          <Trash2 className="h-3.5 w-3.5" /> Delete project
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
        <div className="grid h-fit gap-3">
          {project.documents.map((d) => (
            <WideCard key={d.id} doc={d}>
              <button onClick={() => removeDoc(d.id)} aria-label="Remove from project" className="text-muted hover:text-accent">
                <X className="h-4 w-4" />
              </button>
            </WideCard>
          ))}
          {project.documents.length === 0 && (
            <p className="rounded-lg border border-dashed border-line p-8 text-center text-sm text-muted">
              Empty. Use <Link href="/search" className="underline">Search</Link> and “Add to project”.
            </p>
          )}
        </div>
        {project.documents.length > 0 && (
          <AskPanel
            scope={{ project_id: project.id }}
            title="Ask this project"
            suggestions={["Summarize these sources", "List every date mentioned"]}
          />
        )}
      </div>
    </div>
  );
}
