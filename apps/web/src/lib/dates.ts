import {
  differenceInCalendarDays,
  differenceInHours,
  formatDistanceToNowStrict,
  isBefore,
  startOfDay,
} from "date-fns";
import { formatInTimeZone } from "date-fns-tz";
import type { WorkItem } from "./types";

export const TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata";

export type Urgency = "overdue" | "soon" | "later" | "none" | "done";
export type AgendaGroup = "Overdue" | "Today" | "Tomorrow" | "This week" | "Later" | "No due date";
export const AGENDA_ORDER: AgendaGroup[] = ["Overdue", "Today", "Tomorrow", "This week", "Later", "No due date"];

export const isDone = (w: Pick<WorkItem, "my_status">) =>
  w.my_status === "submitted" || w.my_status === "not_applicable";

export function urgency(w: Pick<WorkItem, "due_at" | "my_status">, now = new Date()): Urgency {
  if (isDone(w)) return "done";
  if (!w.due_at) return "none";
  const due = new Date(w.due_at);
  if (isBefore(due, now)) return "overdue";
  if (differenceInHours(due, now) <= 72) return "soon";
  return "later";
}

export function agendaGroup(w: Pick<WorkItem, "due_at" | "my_status">, now = new Date()): AgendaGroup {
  if (!w.due_at) return "No due date";
  const due = new Date(w.due_at);
  if (isBefore(due, now) && !isDone(w)) return "Overdue";
  const days = differenceInCalendarDays(due, now);
  if (days <= 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days < 7) return "This week";
  return "Later";
}

/** "in 3 days" / "2 hours ago" */
export function relativeDue(iso: string, now = new Date()): string {
  const d = new Date(iso);
  const s = formatDistanceToNowStrict(d, { addSuffix: true });
  if (differenceInCalendarDays(d, now) === 0 && !isBefore(d, now)) return `today, ${formatTime(iso)}`;
  if (differenceInCalendarDays(d, now) === 1) return `tomorrow, ${formatTime(iso)}`;
  return s;
}

export const formatTime = (iso: string) => formatInTimeZone(new Date(iso), TZ, "h:mm a");
/** "Wed 30 Sep, 11:59 PM" */
export const formatAbsolute = (iso: string) => formatInTimeZone(new Date(iso), TZ, "EEE d MMM, h:mm a");
export const formatShortDate = (iso: string) => formatInTimeZone(new Date(iso), TZ, "d MMM");

export function sinceLabel(iso: string | null): string {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 24 ? `${h} h ago` : formatDistanceToNowStrict(new Date(iso), { addSuffix: true });
}

export const deadlineRecentlyChanged = (w: Pick<WorkItem, "due_changed_at">, now = new Date()) =>
  !!w.due_changed_at && differenceInHours(now, new Date(w.due_changed_at)) < 72;

/** Sort key used everywhere: pending first by due date (no date last), then done. */
export function byDue(a: WorkItem, b: WorkItem): number {
  const da = isDone(a) ? 1 : 0;
  const db = isDone(b) ? 1 : 0;
  if (da !== db) return da - db;
  const ta = a.due_at ? new Date(a.due_at).getTime() : Number.POSITIVE_INFINITY;
  const tb = b.due_at ? new Date(b.due_at).getTime() : Number.POSITIVE_INFINITY;
  return ta - tb || a.title.localeCompare(b.title);
}

export const startOfToday = () => startOfDay(new Date());
