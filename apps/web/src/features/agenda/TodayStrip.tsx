import { useSearchParams } from "react-router-dom";
import { cn } from "@/lib/cn";
import { summarize } from "@/lib/items";
import type { WorkItem } from "@/lib/types";

export type StripFilter = "overdue" | "soon" | "review" | null;

export function useStripFilter(): [StripFilter, (f: StripFilter) => void] {
  const [params, setParams] = useSearchParams();
  const f = params.get("f") as StripFilter;
  return [
    f === "overdue" || f === "soon" || f === "review" ? f : null,
    (next) => {
      const p = new URLSearchParams(params);
      if (next) p.set("f", next);
      else p.delete("f");
      setParams(p, { replace: true });
    },
  ];
}

export function TodayStrip({ items, term }: { items: WorkItem[]; term?: string }) {
  const s = summarize(items);
  const [filter, setFilter] = useStripFilter();
  const tiles = [
    { key: "overdue" as const, label: "Overdue", n: s.overdue, tone: s.overdue > 0 ? "text-danger-text" : "text-text" },
    { key: "soon" as const, label: "Due in 72h", n: s.soon, tone: s.soon > 0 ? "text-warning-text" : "text-text" },
    { key: "review" as const, label: "Needs review", n: s.review, tone: s.review > 0 ? "text-accent-text" : "text-text" },
  ];
  const pct = s.total ? Math.round((s.submitted / s.total) * 100) : 0;
  return (
    <section aria-label="Today summary" className="px-4 pt-4 md:px-6">
      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        {tiles.map((t) => (
          <button
            key={t.key}
            onClick={() => setFilter(filter === t.key ? null : t.key)}
            aria-pressed={filter === t.key}
            className={cn(
              "card flex flex-col items-start gap-0.5 px-3 py-3 text-left transition-shadow duration-press hover:shadow-lift sm:px-4",
              filter === t.key && "ring-2 ring-[var(--primary)]",
            )}
          >
            <span className={cn("font-display text-[2rem] leading-none sm:text-h1", t.tone)}>{t.n}</span>
            <span className="micro text-muted">{t.label}</span>
          </button>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-3">
        <div className="h-1 flex-1 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Submitted this term">
          <div className="h-full rounded-full bg-success transition-[width] duration-move ease-ez" style={{ width: `${pct}%` }} />
        </div>
        <span className="shrink-0 text-meta text-muted">
          {term ?? "Term 1"} · {s.submitted} of {s.total} submitted
        </span>
      </div>
    </section>
  );
}
