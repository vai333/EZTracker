import {
  DndContext,
  DragOverlay,
  PointerSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useVirtualizer } from "@tanstack/react-virtual";
import { LayoutGroup, motion, MotionConfig } from "framer-motion";
import { ArrowDownAZ, CalendarArrowDown, ChevronDown, Eye, EyeOff, MoreHorizontal } from "lucide-react";
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Button, CourseDot, EmptyState, Input, Skeleton } from "@/components/ui/primitives";
import { Dialog, Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from "@/components/ui/overlays";
import { cn } from "@/lib/cn";
import { isDone, urgency } from "@/lib/dates";
import { boardColumns, courseLabel, itemsFor } from "@/lib/items";
import { useCourses, useItems, useMoveItem, usePatchCourse } from "@/lib/queries";
import { useUI } from "@/lib/store";
import type { Course, WorkItem } from "@/lib/types";
import { TodayStrip, useStripFilter, type StripFilter } from "../agenda/TodayStrip";
import { ItemCard } from "./ItemCard";

export const NEEDS_REVIEW = "needs-review";
const EASE = [0.2, 0.8, 0.2, 1] as const;

/**
 * Keyboard moving (D-015): Space lifts the focused card, ←/→ choose a column, Space/Enter drops, Esc cancels.
 * dnd-kit's KeyboardSensor scrolls horizontally-scrolling containers instead of moving between columns, so
 * pointer/touch use dnd-kit and the keyboard uses this small, deterministic state machine.
 */
interface KbMove {
  liftedId: string | null;
  lift: (item: WorkItem) => void;
}
const KbContext = createContext<KbMove>({ liftedId: null, lift: () => {} });

function DraggableCard({ item, course, courses, inReview }: { item: WorkItem; course: Course | null; courses: Course[]; inReview: boolean }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: item.id, data: { item } });
  const kb = useContext(KbContext);
  const lifted = kb.liftedId === item.id;
  return (
    <motion.div layout="position" layoutId={item.id} transition={{ duration: 0.24, ease: EASE }}>
      <ItemCard
        ref={setNodeRef}
        item={item}
        course={course}
        courses={courses}
        inReview={inReview}
        dragging={isDragging}
        {...attributes}
        {...listeners}
        onKeyDown={(e) => {
          if (e.key === " " && !kb.liftedId && e.target === e.currentTarget) {
            e.preventDefault();
            kb.lift(item);
          }
        }}
        className={cn(lifted && "scale-[1.02] shadow-lift ring-2 ring-[var(--primary)]")}
        aria-roledescription="movable card"
        aria-describedby="kb-move-help"
      />
    </motion.div>
  );
}

function VirtualList({ items, render }: { items: WorkItem[]; render: (w: WorkItem) => React.ReactNode }) {
  const parent = useRef<HTMLDivElement>(null);
  const v = useVirtualizer({ count: items.length, getScrollElement: () => parent.current, estimateSize: () => 112, overscan: 6 });
  return (
    <div ref={parent} className="max-h-[70vh] overflow-y-auto">
      <div style={{ height: v.getTotalSize(), position: "relative" }}>
        {v.getVirtualItems().map((r) => (
          <div key={r.key} data-index={r.index} ref={v.measureElement} className="absolute inset-x-0 pb-2" style={{ transform: `translateY(${r.start}px)` }}>
            {render(items[r.index]!)}
          </div>
        ))}
      </div>
    </div>
  );
}

function applyFilter(items: WorkItem[], f: StripFilter, hideInfo: boolean) {
  return items.filter((w) => {
    if (hideInfo && w.kind === "info" && w.course_id !== null) return false;
    if (f === "overdue") return urgency(w) === "overdue";
    if (f === "soon") return urgency(w) === "soon";
    return true;
  });
}

function Column({ id, course, items, courses, isOverTarget }: { id: string; course: Course | null; items: WorkItem[]; courses: Course[]; isOverTarget: boolean }) {
  const { setNodeRef } = useDroppable({ id, data: { courseId: course?.id ?? null } });
  const [showDone, setShowDone] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const patchCourse = usePatchCourse();
  const pending = items.filter((w) => !isDone(w));
  const done = items.filter(isDone);
  const soon = pending.filter((w) => ["soon", "overdue"].includes(urgency(w))).length;
  const review = course === null;
  const render = (w: WorkItem) => <DraggableCard item={w} course={course} courses={courses} inReview={review} />;

  return (
    <section
      ref={setNodeRef}
      data-col={id}
      aria-label={`${review ? "Needs Review" : course!.name} column`}
      className={cn(
        "well snap-col flex w-[calc(100vw-48px)] shrink-0 flex-col p-2 transition-[box-shadow,background] duration-press sm:w-[320px]",
        isOverTarget && "shadow-[inset_0_0_0_2px_var(--primary)]",
      )}
    >
      <header className="flex items-start gap-2 px-2 pb-2 pt-1.5">
        <CourseDot index={course?.color_index ?? null} className="mt-2.5" />
        <div className="min-w-0 flex-1">
          <h2 className={cn("truncate font-display text-h3", review && "text-accent-text")} title={course?.name}>
            {review ? "Needs Review" : courseLabel(course)}
          </h2>
          <p className="text-meta text-muted">
            {pending.length} pending{soon ? ` · ${soon} due soon` : ""}
          </p>
        </div>
        {course && (
          <Menu>
            <MenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={`${courseLabel(course)} options`}>
                <MoreHorizontal size={16} strokeWidth={1.5} />
              </Button>
            </MenuTrigger>
            <MenuContent>
              <MenuItem onSelect={() => setRenaming(true)}>Rename short name…</MenuItem>
              <MenuSeparator />
              <MenuLabel>Colour</MenuLabel>
              <div className="flex gap-1.5 px-2.5 pb-2">
                {Array.from({ length: 8 }, (_, i) => (
                  <button
                    key={i}
                    aria-label={`Colour ${i + 1}`}
                    aria-pressed={course.color_index === i}
                    onClick={() => patchCourse.mutate({ id: course.id, patch: { color_index: i } })}
                    className={cn("h-6 w-6 rounded-full border-2", course.color_index === i ? "border-text" : "border-transparent")}
                    style={{ background: `var(--course-${i})` }}
                  />
                ))}
              </div>
              <MenuSeparator />
              <MenuItem onSelect={() => patchCourse.mutate({ id: course.id, patch: { is_archived: true } })}>Archive course</MenuItem>
            </MenuContent>
          </Menu>
        )}
      </header>
      <div className="flex min-h-24 flex-col gap-2">
        {pending.length === 0 && done.length === 0 && (
          review ? <EmptyState title="All sorted. Nice." body="New notifications EZTracker isn't sure about will land here." />
            : <p className="px-2 py-6 text-center text-small text-faint">Nothing here yet. Drop a card to file it.</p>
        )}
        {pending.length > 50 ? <VirtualList items={pending} render={render} /> : pending.map((w) => <div key={w.id}>{render(w)}</div>)}
      </div>
      {done.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setShowDone((v) => !v)}
            aria-expanded={showDone}
            className="flex h-9 w-full items-center gap-1.5 rounded-lg px-2 text-small text-muted hover:bg-surface"
          >
            <ChevronDown size={14} strokeWidth={1.5} className={cn("transition-transform duration-toggle", !showDone && "-rotate-90")} />
            Submitted ({done.length})
          </button>
          {showDone && <div className="flex flex-col gap-2 pt-1">{done.map((w) => <div key={w.id}>{render(w)}</div>)}</div>}
        </div>
      )}
      {course && (
        <RenameDialog open={renaming} onOpenChange={setRenaming} course={course}
          onSave={(v) => patchCourse.mutate({ id: course.id, patch: { short_name: v || null } })} />
      )}
    </section>
  );
}

function RenameDialog({ open, onOpenChange, course, onSave }: { open: boolean; onOpenChange: (v: boolean) => void; course: Course; onSave: (v: string) => void }) {
  const [v, setV] = useState(course.short_name ?? "");
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Short name" description={course.name}>
      <form onSubmit={(e) => { e.preventDefault(); onSave(v.trim()); onOpenChange(false); }} className="flex gap-2">
        <Input autoFocus value={v} maxLength={40} onChange={(e) => setV(e.target.value)} aria-label="Short name" />
        <Button variant="primary">Save</Button>
      </form>
    </Dialog>
  );
}

export default function BoardView() {
  const { data: courses, isLoading: lc } = useCourses();
  const { data: items, isLoading: li } = useItems();
  const move = useMoveItem();
  const { hideInfo, setHideInfo, boardOrder, setBoardOrder } = useUI();
  const [filter] = useStripFilter();
  const [active, setActive] = useState<WorkItem | null>(null);
  const [overId, setOverId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 6 } }),
  );

  const cols = useMemo(() => boardColumns(courses ?? [], items ?? [], boardOrder), [courses, items, boardOrder]);
  const [kb, setKb] = useState<{ item: WorkItem; col: number } | null>(null);
  const [live, setLive] = useState("");
  const colIds = useMemo(() => [NEEDS_REVIEW, ...(filter === "review" ? [] : cols.map((c) => c.id))], [cols, filter]);
  const colIdOf = (w: WorkItem) => w.course_id ?? NEEDS_REVIEW;

  useEffect(() => {
    if (!kb) return;
    const onKey = (e: KeyboardEvent) => {
      const key = e.key;
      if (key === "ArrowRight" || key === "ArrowLeft") {
        e.preventDefault();
        const col = Math.max(0, Math.min(colIds.length - 1, kb.col + (key === "ArrowRight" ? 1 : -1)));
        setKb({ ...kb, col });
        document.querySelector(`[data-col="${colIds[col]}"]`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
        setLive(`"${kb.item.title}" is over ${colName(colIds[col])}.`);
      } else if (key === " " || key === "Enter") {
        e.preventDefault();
        const target = colIds[kb.col]!;
        setKb(null);
        const courseId = target === NEEDS_REVIEW ? null : target;
        if (courseId !== kb.item.course_id) {
          const c = courses?.find((x) => x.id === courseId);
          move.mutate({ id: kb.item.id, courseId, label: c ? courseLabel(c) : "Needs Review" });
          setLive(`Moved "${kb.item.title}" to ${colName(target)}.`);
        } else setLive(`"${kb.item.title}" was dropped back where it was.`);
      } else if (key === "Escape" || key === "Tab") {
        if (key === "Escape") e.preventDefault();
        setKb(null);
        setLive(`Moving "${kb.item.title}" was cancelled.`);
      } else if (key === "ArrowUp" || key === "ArrowDown") {
        e.preventDefault(); // order inside a column is by due date; nothing to reorder
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kb, colIds, courses]);

  const kbCtx = useMemo<KbMove>(() => ({
    liftedId: kb?.item.id ?? null,
    lift: (item) => {
      const col = Math.max(0, colIds.indexOf(colIdOf(item)));
      setKb({ item, col });
      setLive(`Picked up "${item.title}". Use left and right arrows to choose a column, space to drop, escape to cancel.`);
    },
     
  }), [kb, colIds]);
  const colName = (id: string | number | undefined | null) => {
    if (id === NEEDS_REVIEW) return "Needs Review";
    const c = courses?.find((x) => x.id === id);
    return c ? c.name : "nowhere";
  };
  const titleOf = (id: string | number) => items?.find((w) => w.id === id)?.title ?? "card";

  const announcements: Announcements = {
    onDragStart: ({ active: a }) => `Picked up "${titleOf(a.id)}". Use left and right arrows to choose a column, space to drop, escape to cancel.`,
    onDragOver: ({ active: a, over }) => (over ? `"${titleOf(a.id)}" is over ${colName(over.id)}.` : `"${titleOf(a.id)}" is not over a column.`),
    onDragEnd: ({ active: a, over }) => (over ? `Moved "${titleOf(a.id)}" to ${colName(over.id)}.` : `"${titleOf(a.id)}" was dropped and returned.`),
    onDragCancel: ({ active: a }) => `Moving "${titleOf(a.id)}" was cancelled.`,
  };

  const onEnd = (e: DragEndEvent) => {
    setActive(null);
    setOverId(null);
    if (!e.over) return;
    const item = e.active.data.current?.item as WorkItem | undefined;
    const courseId = e.over.id === NEEDS_REVIEW ? null : String(e.over.id);
    if (!item || item.course_id === courseId) return;
    const c = courses?.find((x) => x.id === courseId);
    move.mutate({ id: item.id, courseId, label: c ? courseLabel(c) : "Needs Review" });
  };

  if (lc || li) {
    return (
      <div className="flex gap-3 overflow-hidden p-4 md:p-6" aria-busy>
        {[0, 1, 2].map((i) => (
          <div key={i} className="well w-[320px] shrink-0 space-y-2 p-2">
            <Skeleton className="h-10" />
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
        ))}
      </div>
    );
  }

  const all = applyFilter(items ?? [], filter, hideInfo);
  const showOnlyReview = filter === "review";

  return (
    <>
      <TodayStrip items={items ?? []} />
      <div className="flex flex-wrap items-center gap-2 px-4 pt-4 md:px-6">
        <Button size="sm" variant="ghost" onClick={() => setBoardOrder(boardOrder === "due" ? "alpha" : "due")} aria-label={`Order columns ${boardOrder === "due" ? "alphabetically" : "by nearest due date"}`}>
          {boardOrder === "due" ? <CalendarArrowDown size={15} strokeWidth={1.5} /> : <ArrowDownAZ size={15} strokeWidth={1.5} />}
          {boardOrder === "due" ? "By nearest due" : "A–Z"}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setHideInfo(!hideInfo)} aria-pressed={hideInfo}>
          {hideInfo ? <EyeOff size={15} strokeWidth={1.5} /> : <Eye size={15} strokeWidth={1.5} />}
          {hideInfo ? "Info hidden" : "Hide info"}
        </Button>
        <span className="ml-auto hidden text-meta text-faint lg:inline">Drag a card to re-file it · or press M on a card</span>
      </div>
      <p id="kb-move-help" className="sr-only">Press space to pick up this card, left and right arrows to choose a column, space to drop, escape to cancel. Press M for a Move to menu, Enter to open.</p>
      <div aria-live="assertive" className="sr-only">{live}</div>
      <KbContext.Provider value={kbCtx}>
      <MotionConfig reducedMotion="user">
        <DndContext
          sensors={sensors}
          accessibility={{ announcements, screenReaderInstructions: { draggable: "Press space to pick up this card, left and right arrows to choose a column, space to drop, escape to cancel. Or press M for a Move to menu." } }}
          onDragStart={(e: DragStartEvent) => setActive((e.active.data.current?.item as WorkItem) ?? null)}
          onDragOver={(e) => setOverId(e.over ? String(e.over.id) : null)}
          onDragEnd={onEnd}
          onDragCancel={() => { setActive(null); setOverId(null); }}
        >
          <LayoutGroup>
            <div className="scroll-snap-x mt-3 flex scroll-px-4 items-start gap-3 overflow-x-auto px-4 pb-6 md:scroll-px-6 md:px-6" aria-label="Board columns">
              <Column id={NEEDS_REVIEW} course={null} items={itemsFor(all, null)} courses={courses ?? []} isOverTarget={overId === NEEDS_REVIEW || (!!kb && colIds[kb.col] === NEEDS_REVIEW)} />
              {!showOnlyReview && cols.map((c) => (
                <Column key={c.id} id={c.id} course={c} items={itemsFor(all, c.id)} courses={courses ?? []} isOverTarget={overId === c.id || (!!kb && colIds[kb.col] === c.id)} />
              ))}
            </div>
          </LayoutGroup>
          <DragOverlay dropAnimation={{ duration: 240, easing: "cubic-bezier(.2,.8,.2,1)" }}>
            {active ? (
              <div className="w-[300px]">
                <ItemCard item={active} course={courses?.find((c) => c.id === active.course_id) ?? null} courses={courses ?? []} overlay inReview={active.course_id === null} />
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      </MotionConfig>
      </KbContext.Provider>
    </>
  );
}
