/* eslint-disable @next/next/no-img-element */
import { Images } from "lucide-react";
import { apiSrc, type Category } from "@/lib/api";

/** Cover made of the category's most recent photos (1, 2 or 4 tiles). */
export function Collage({ category, className = "" }: { category: Category; className?: string }) {
  const covers = category.covers.slice(0, category.covers.length >= 4 ? 4 : Math.min(category.covers.length, 2));
  if (!covers.length)
    return (
      <div className={`grid place-items-center ${className}`} style={{ background: `${category.color}1f` }}>
        <Images className="h-8 w-8" style={{ color: category.color }} />
      </div>
    );
  return (
    <div className={`grid gap-0.5 overflow-hidden ${covers.length === 1 ? "grid-cols-1" : "grid-cols-2"} ${className}`}>
      {covers.map((src) => (
        <img key={src} src={apiSrc(src)} alt="" loading="lazy" className="h-full min-h-0 w-full object-cover" />
      ))}
    </div>
  );
}
