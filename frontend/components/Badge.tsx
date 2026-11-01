import type { Category } from "@/lib/api";

export function Badge({ category }: { category: Category | null }) {
  if (!category) return <span className="eyebrow">Uncategorized</span>;
  return (
    <span
      className="inline-block rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide"
      style={{ background: `${category.color}22`, color: category.color }}
    >
      {category.name}
    </span>
  );
}
