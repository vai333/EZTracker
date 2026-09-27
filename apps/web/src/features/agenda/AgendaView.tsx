import { Diamond, NotebookPen, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Button, EmptyState, Pill, Skeleton, StatusToggle } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { AGENDA_ORDER, agendaGroup, byDue, deadlineRecentlyChanged, isDone, urgency, type AgendaGroup } from "@/lib/dates";
import { courseLabel, isNeedsReview, isTask } from "@/lib/items";
import { useCourses, useItems, useSetStatus } from "@/lib/queries";
import { useUI } from "@/lib/store";
import type { Course, WorkItem } from "@/lib/types";
import { KIND_LABEL } from "@/lib/types";
import { DueLine } from "../board/ItemCard";
import { NewItemDialog } from "../item/NewItemDialog";
import { TodayStrip, useStripFilter } from "./TodayStrip";

const GROUP_TONE: Partial<Record<AgendaGroup, string>> = { Overdue: "text-danger-text", Today: "text-warning-text" };

function Row({ item, course }: { item: WorkItem; course: Course | undefined }) {
  const openItem = useUI((s) => s.openItem);
  const density = useUI((s) => s.density);
  const status = useSetStatus();
  const done = isDone(item);
  return (
    <li
      className={cn(
        "group relative flex items-center gap-3 border-b border-border pl-4 pr-2 last:border-b-0 hover:bg-surface-2",
        density === "compact" ? "min-h-11 py-1" : "min-h-14 py-2",
      )}
    >
      <span aria-hidden className="absolute inset-y-2 left-0 w-[3px] rounded-full" style={{ background: course ? `var(--course-${course.color_index % 8})` : "var(--accent)" }} />
      <StatusToggle status={item.my_status} label={item.title}
        onToggle={() => status.mutate({ id: item.id, status: item.my_status === "submitted" ? "pending" : "submitted" })} />
      <button onClick={() => openItem(item.id)} className="flex min-w-0 flex-1 flex-col items-start gap-0.5 text-left md:flex-row md:items-center md:gap-3">
        <span className={cn("min-w-0 max-w-full truncate text-body font-medium text-text md:flex-1", done && "text-muted line-through decoration-1")}>
          {item.title}
        </span>
        <span className="flex shrink-0 flex-wrap items-center gap-2">
          <span className="text-small text-muted">{courseLabel(course ?? null)}</span>
          <Pill>{KIND_LABEL[item.kind]}</Pill>
          {deadlineRecentlyChanged(item) && <Pill tone="warning">Deadline changed</Pill>}
          <DueLine item={item} className="md:w-40 md:justify-end" />
        </span>
      </button>
      <span className="flex w-5 shrink-0 justify-center text-faint">
        {item.origin === "notification_only" ? <Diamond size={12} strokeWidth={1.5} aria-label="From a notification only" /> :
          item.my_note ? <NotebookPen size={13} strokeWidth={1.5} aria-label="Has a note" /> : null}
      </span>
    </li>
  );
}

export default function AgendaView() {
  const { data: items, isLoading } = useItems();
  const { data: courses = [] } = useCourses();
  const [filter] = useStripFilter();
  const [showDone, setShowDone] = useState(false);
  const [adding, setAdding] = useState(false);
  const courseById = useMemo(() => new Map(courses.map((c) => [c.id, c])), [courses]);

  const groups = useMemo(() => {
    const visible = (items ?? []).filter((w) => {
      if (w.is_hidden) return false;
      if (!isTask(w) && !w.due_at) return false; // info items only appear here when they carry a date
      if (!showDone && isDone(w)) return false;
      if (filter === "overdue") return urgency(w) === "overdue";
      if (filter === "soon") return urgency(w) === "soon";
      if (filter === "review") return isNeedsReview(w);
      return true;
    });
    const map = new Map<AgendaGroup, WorkItem[]>();
    for (const w of visible.sort(byDue)) {
      const g = agendaGroup(w);
      map.set(g, [...(map.get(g) ?? []), w]);
    }
    return AGENDA_ORDER.filter((g) => map.has(g)).map((g) => ({ g, list: map.get(g)! }));
  }, [items, filter, showDone]);

  if (isLoading) {
    return (
      <div className="space-y-3 p-4 md:p-6" aria-busy>
        <div className="grid grid-cols-3 gap-3"><Skeleton className="h-20" /><Skeleton className="h-20" /><Skeleton className="h-20" /></div>
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}
      </div>
    );
  }

  return (
    <>
      <TodayStrip items={items ?? []} />
      <div className="mx-auto max-w-4xl px-4 pb-8 pt-4 md:px-6">
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={() => setShowDone(!showDone)} aria-pressed={showDone}>
            {showDone ? "Hide submitted" : "Show submitted"}
          </Button>
          <div className="flex-1" />
          <Button size="sm" onClick={() => setAdding(true)}><Plus size={15} strokeWidth={1.5} />Add item</Button>
        </div>
        {groups.length === 0 ? (
          <EmptyState
            title={filter ? "Nothing matches this filter." : "You're clear."}
            body={filter ? "Tap the tile again to clear the filter." : "Nothing pending with a deadline. New work from Nexus shows up here after each sync."}
          />
        ) : (
          groups.map(({ g, list }) => (
            <section key={g} aria-labelledby={`ag-${g}`} className="mt-5">
              <h2 id={`ag-${g}`} className={cn("mb-2 flex items-baseline gap-2 font-display text-h3", GROUP_TONE[g])}>
                {g}
                <span className="font-ui text-meta text-faint">{list.length}</span>
              </h2>
              <ul className="card overflow-hidden p-0">
                {list.map((w) => <Row key={w.id} item={w} course={w.course_id ? courseById.get(w.course_id) : undefined} />)}
              </ul>
            </section>
          ))
        )}
      </div>
      <NewItemDialog open={adding} onOpenChange={setAdding} />
    </>
  );
}
