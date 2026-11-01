/* eslint-disable @next/next/no-img-element */
import { FileText, Loader2, TriangleAlert } from "lucide-react";
import { fileSrc, type Doc } from "@/lib/api";

export function Thumb({ doc, className = "" }: { doc: Doc; className?: string }) {
  const busy = doc.status === "pending" || doc.status === "processing";
  return (
    <div className={`relative overflow-hidden bg-[#e6ebe4] ${className}`}>
      {doc.mime.startsWith("image/") ? (
        <img src={fileSrc(doc)} alt={doc.title} loading="lazy" className="h-full w-full object-cover" />
      ) : (
        <div className="grid h-full w-full place-items-center bg-[#efeadf]">
          <FileText className="h-7 w-7 text-black/30" />
        </div>
      )}
      {busy && (
        <div className="absolute inset-0 grid place-items-center bg-white/60">
          <Loader2 className="h-5 w-5 animate-spin text-ink" />
        </div>
      )}
      {doc.status === "failed" && (
        <div className="absolute inset-0 grid place-items-center bg-white/70" title={doc.error}>
          <TriangleAlert className="h-5 w-5 text-accent" />
        </div>
      )}
    </div>
  );
}
