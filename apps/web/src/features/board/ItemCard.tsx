import { CalendarClock, Diamond, FolderInput, NotebookPen, Sparkles, Wand2 } from "lucide-react";
import { forwardRef, type HTMLAttributes } from "react";
import { CourseDot, Pill, StatusToggle, Tip } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { deadlineRecentlyChanged, formatAbsolute, relativeDue, urgency } from "@/lib/dates";
import { suggestions } from "@/lib/items";
import { useMoveItem, useSetStatus } from "@/lib/queries";
import { useUI } from "@/lib/store";
import type { Course, WorkItem } from "@/lib/types";
import { KIND_LABEL } from "@/lib/types";

export function DueLine({ item, className }: { item: WorkItem; className?: string }) {
  if (!item.due_at) return <span className={cn("text-small text-faint", className)}>No due date</span>;
  const u = urgency(item);
  return (
    <Tip content={<span>{formatAbsolute(item.due_at)}{item.due_source === "parsed_from_text" && " · read from the announcement text"}{item.due_source === "user" && " · set by you"}</span>}>
      <span
        className={cn(
          "inline-flex items-center gap-1 text-small",
          u === "overdue" && "font-medium text-danger-text",
          u === "soon" && "font-medium text-warning-text",
          (u === "later" || u === "none") && "text-muted",
          u === "done" && "text-faint line-through decoration-1",
          className,
        )}
      >
        <CalendarClock size={14} strokeWidth={1.5} aria-hidden />
        {u === "overdue" && <span className="sr-only">Overdue:</span>}
        {relativeDue(item.due_at)}
        {item.due_source === "parsed_from_text" && (
          <span className="rounded bg-[color-mix(in_oklab,var(--info)_12%,transparent)] px-1 text-meta text-info-text">parsed</span>
        )}
      </span>
    </Tip>
  );
}

export function ConfidenceDot({ item }: { item: WorkItem }) {
  if (item.classification !== "auto" || item.confidence == null || item.confidence >= 0.85) return null;
  const top = item.classifier_reasons?.[0];
  return (
    <Tip
      content={
        <div className="space-y-1">
          <p className="font-medium">Auto-filed at {Math.round(item.confidence * 100)}% confidence</p>
          {top?.reasons.map((r) => <p key={r} className="text-muted">{r}</p>)}
        </div>
      }
    >
      <span tabIndex={0} aria-label={`Auto-filed, ${Math.round(item.confidence * 100)}% confidence`} className="grid h-6 w-6 place-items-center">
        <span className="h-1.5 w-1.5 rounded-full bg-accent" />
      </span>
    </Tip>
  );
}

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  item: WorkItem;
  course?: Course | null;
  courses: Course[];
  inReview?: boolean;
  dragging?: boolean;
  overlay?: boolean;
}

export const ItemCard = forwardRef<HTMLDivElement, CardProps>(function ItemCard(
  { item, course, courses, inReview, dragging, overlay, className, onKeyDown: dndKeyDown, ...rest }, ref,
) {
  const openItem = useUI((s) => s.openItem);
  const setMoveTarget = useUI((s) => s.setMoveTarget);
  const status = useSetStatus();
  const move = useMoveItem();
  const done = item.my_status === "submitted" || item.my_status === "not_applicable";
  const info = item.kind === "info";
  const sugg = inReview ? suggestions(item, courses) : [];
  const originIcon = item.origin === "notification_only"
    ? <Tip content="From a notification only — not in My Work"><Diamond size={12} strokeWidth={1.5} aria-label="Notification only" className="text-faint" /></Tip>
    : item.origin === "manual" ? <Tip content="Added by you"><NotebookPen size={12} strokeWidth={1.5} aria-label="Added by you" className="text-faint" /></Tip> : null;

  const toggle = () => status.mutate({ id: item.id, status: item.my_status === "submitted" ? "pending" : "submitted" });

  if (info && !inReview) {
    return (
      <div
        ref={ref}
        role="button"
        tabIndex={0}
        onClick={() => openItem(item.id)}
        onKeyDown={(e) => {
          dndKeyDown?.(e);
          if (e.key === "Enter") openItem(item.id);
        }}
        className={cn(
          "group flex min-h-10 cursor-pointer items-center gap-2 rounded-card border border-transparent px-3 py-2 text-small text-muted hover:border-border hover:bg-surface",
          dragging && "opacity-40",
          overlay && "card shadow-lift",
          className,
        )}
        style={{ borderLeft: `3px solid var(--course-${(course?.color_index ?? 0) % 8})` }}
        {...rest}
      >
        <span className="micro shrink-0 text-faint">Info</span>
        <span className="min-w-0 flex-1 truncate">{item.title}</span>
        {originIcon}
      </div>
    );
  }

  return (
    <div
      ref={ref}
      role="button"
      tabIndex={0}
      aria-label={`${item.title}${item.due_at ? `, due ${relativeDue(item.due_at)}` : ""}${done ? ", submitted" : ""}`}
      onClick={() => openItem(item.id)}
      onKeyDown={(e) => {
        dndKeyDown?.(e); // dnd-kit keyboard sensor (space to lift) — compose, don't override
        if (e.defaultPrevented) return;
        if (e.key === "Enter") openItem(item.id);
        if (e.key.toLowerCase() === "m" && !e.metaKey && !e.ctrlKey) {
          e.preventDefault();
          setMoveTarget(item.id);
        }
      }}
      className={cn(
        "card group relative cursor-pointer select-none overflow-hidden p-3 pl-4 transition-[box-shadow,transform,opacity] duration-press ease-ez",
        "hover:shadow-lift",
        done && "opacity-60",
        dragging && "opacity-40",
        overlay && "rotate-[.6deg] scale-[1.02] shadow-lift",
        className,
      )}
      {...rest}
    >
      <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]" style={{ background: course ? `var(--course-${course.color_index % 8})` : "var(--accent)" }} />
      <div className="flex items-center gap-1.5">
        <span className="micro text-faint">{KIND_LABEL[item.kind]}</span>
        {originIcon}
        <span className="flex-1" />
        {item.upstream_updated_at && <Pill tone="info">Updated</Pill>}
        <ConfidenceDot item={item} />
        <Tip content="Move to… (M)">
          <button
            type="button"
            aria-label={`Move "${item.title}" to…`}
            onClick={(e) => {
              e.stopPropagation();
              setMoveTarget(item.id);
            }}
            onPointerDown={(e) => e.stopPropagation()}
            className="grid h-7 w-7 place-items-center rounded-md text-faint opacity-100 hover:bg-surface-2 hover:text-text md:opacity-0 md:focus-visible:opacity-100 md:group-hover:opacity-100"
          >
            <FolderInput size={15} strokeWidth={1.5} />
          </button>
        </Tip>
      </div>
      <p className={cn("mt-1 line-clamp-2 text-body font-medium text-text", done && "line-through decoration-1")}>{item.title}</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
        <StatusToggle status={item.my_status} onToggle={toggle} label={item.title} />
        <DueLine item={item} />
        {deadlineRecentlyChanged(item) && <Pill tone="warning">Deadline changed</Pill>}
        {item.upstream_due_at && item.due_source === "user" && <Pill tone="info">Nexus date differs</Pill>}
        {item.my_note && <Tip content={item.my_note}><NotebookPen size={14} strokeWidth={1.5} className="text-faint" aria-label="Has a note" /></Tip>}
      </div>
      {inReview && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {sugg.length > 0 ? (
            <>
              <span className="inline-flex items-center gap-1 text-meta text-faint"><Wand2 size={12} strokeWidth={1.5} />Suggested:</span>
              {sugg.map((s) => {
                const c = courses.find((x) => x.id === s.course_id);
                return (
                  <button
                    key={s.course_id}
                    type="button"
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={(e) => {
                      e.stopPropagation();
                      move.mutate({ id: item.id, courseId: s.course_id, label: c?.short_name || c?.name || "course" });
                    }}
                    className="inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface-2 px-2.5 text-meta font-medium text-text hover:border-accent"
                  >
                    <CourseDot index={c?.color_index} />
                    {c?.short_name || s.course}
                  </button>
                );
              })}
            </>
          ) : (
            <span className="inline-flex items-center gap-1 text-meta text-faint"><Sparkles size={12} strokeWidth={1.5} />No good guess — drag it where it belongs</span>
          )}
        </div>
      )}
    </div>
  );
});
