import Link from "next/link";
import { Thumb } from "./Thumb";
import { Badge } from "./Badge";
import { timeAgo, type Doc } from "@/lib/api";

export function RecentCard({ doc }: { doc: Doc }) {
  return (
    <Link
      href={`/photo/${doc.id}`}
      className="group w-40 shrink-0 overflow-hidden rounded-lg border border-line bg-card transition hover:shadow-md md:w-auto"
    >
      <div className="relative">
        <Thumb doc={doc} className="h-24 w-full" />
        {doc.category && (
          <span className="absolute left-1.5 top-1.5 max-w-[85%] truncate rounded bg-ink/85 px-1.5 py-0.5 font-mono text-[9px] uppercase text-white">
            {doc.category.name}
          </span>
        )}
      </div>
      <div className="p-2.5">
        <p className="truncate text-xs font-medium">{doc.status === "ready" ? doc.title : doc.filename}</p>
        <p className="font-mono text-[10px] text-muted">{doc.status === "ready" ? timeAgo(doc.created_at) : doc.status}</p>
      </div>
    </Link>
  );
}

export function WideCard({ doc, snippet, children }: { doc: Doc; snippet?: string; children?: React.ReactNode }) {
  return (
    <div className="relative flex gap-4 rounded-lg border border-line bg-card p-4 transition hover:shadow-md">
      <Link href={`/photo/${doc.id}`} className="absolute inset-0" aria-label={doc.title} />
      <Thumb doc={doc} className="h-20 w-24 shrink-0 rounded-md md:h-24 md:w-28" />
      <div className="min-w-0 flex-1">
        {doc.category || doc.status !== "ready" ? <Badge category={doc.category} /> : <span className="eyebrow">Needs a category</span>}
        <h3 className="mt-1.5 font-serif text-lg leading-tight">{doc.title}</h3>
        <p className="mt-1 line-clamp-2 text-xs text-muted">{snippet ?? doc.summary}</p>
      </div>
      {children && <div className="relative z-10 shrink-0">{children}</div>}
    </div>
  );
}
