import { differenceInHours } from "date-fns";
import { byDue, isDone } from "./dates";
import type { Course, WorkItem } from "./types";
import { TASK_KINDS } from "./types";

export const isTask = (w: WorkItem) => TASK_KINDS.includes(w.kind);
export const isNeedsReview = (w: WorkItem) => w.course_id === null && !w.is_hidden;

export function courseLabel(c: Course | undefined | null): string {
  return c ? c.short_name || c.name : "Needs Review";
}

export interface Summary {
  overdue: number;
  soon: number;
  review: number;
  submitted: number;
  total: number;
}

export function summarize(items: WorkItem[], now = new Date()): Summary {
  let overdue = 0, soon = 0, review = 0, submitted = 0, total = 0;
  for (const w of items) {
    if (w.is_hidden) continue;
    if (isNeedsReview(w)) review++;
    if (!isTask(w) && w.kind !== "event") continue;
    total++;
    if (w.my_status === "submitted") submitted++;
    if (isDone(w) || !w.due_at) continue;
    const h = differenceInHours(new Date(w.due_at), now);
    if (new Date(w.due_at) < now) overdue++;
    else if (h <= 72) soon++;
  }
  return { overdue, soon, review, submitted, total };
}

/** Board columns: Needs Review first, then active courses by nearest pending due date (or A–Z). */
export function boardColumns(courses: Course[], items: WorkItem[], order: "due" | "alpha") {
  const active = courses.filter((c) => !c.is_archived);
  const nearest = new Map<string, number>();
  for (const w of items) {
    if (!w.course_id || isDone(w) || !w.due_at || w.is_hidden) continue;
    const t = new Date(w.due_at).getTime();
    nearest.set(w.course_id, Math.min(nearest.get(w.course_id) ?? Infinity, t));
  }
  const sorted = [...active].sort((a, b) =>
    order === "alpha"
      ? courseLabel(a).localeCompare(courseLabel(b))
      : (nearest.get(a.id) ?? Infinity) - (nearest.get(b.id) ?? Infinity) || courseLabel(a).localeCompare(courseLabel(b)),
  );
  return sorted;
}

export function itemsFor(items: WorkItem[], courseId: string | null) {
  return items.filter((w) => !w.is_hidden && w.course_id === courseId).sort(byDue);
}

export function suggestions(w: WorkItem, courses: Course[]) {
  const ids = new Set(courses.filter((c) => !c.is_archived).map((c) => c.id));
  return (w.classifier_reasons ?? []).filter((r) => r.course_id && ids.has(r.course_id)).slice(0, 2);
}
