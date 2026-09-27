export type WorkKind =
  | "assignment" | "workbook" | "async_assignment" | "form" | "announcement_task" | "exam" | "event" | "info";
export type Origin = "assignments_tab" | "notification_only" | "both" | "manual";
export type MyStatus = "pending" | "in_progress" | "submitted" | "not_applicable";
export type ClassStatus = "auto" | "manual" | "unresolved";
export type RunStatus = "running" | "success" | "partial" | "failed";

export interface Course {
  id: string;
  name: string;
  short_name: string | null;
  instructor: string | null;
  category: "core" | "soft_skills" | "elective" | "other" | null;
  mode: string | null;
  term: string | null;
  color_index: number;
  is_archived: boolean;
}

export interface ClassifierReason {
  course_id: string | null;
  course: string | null;
  score: number;
  reasons: string[];
}

export interface Link {
  label: string;
  url: string;
}

export interface WorkItem {
  id: string;
  course_id: string | null;
  title: string;
  kind: WorkKind;
  origin: Origin;
  due_at: string | null;
  due_source: "nexus_field" | "parsed_from_text" | "user" | null;
  instructions_md: string | null;
  links: Link[];
  nexus_status: string | null;
  my_status: MyStatus;
  my_status_set_by: "default" | "user";
  my_note: string | null;
  classification: ClassStatus;
  confidence: number | null;
  classifier_reasons: ClassifierReason[];
  is_hidden: boolean;
  upstream_due_at: string | null;
  due_changed_at: string | null;
  upstream_updated_at: string | null;
  first_seen_at: string;
  updated_at: string;
}

export interface SourceNotification {
  id: string;
  title: string | null;
  snippet: string | null;
  category_raw: string | null;
  published_at: string | null;
  link_url: string | null;
}

export interface ItemEvent {
  id: string | number;
  actor: "scraper" | "user";
  event: string;
  from_value: unknown;
  to_value: unknown;
  created_at: string;
}

export interface ItemDetail {
  sources: SourceNotification[];
  events: ItemEvent[];
}

export interface SyncRun {
  id: string;
  trigger: "schedule" | "manual";
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  stats: Record<string, unknown> & { coverage?: Coverage };
  surface_errors: { surface: string; strategy: string; level?: string; message: string }[];
}

export interface Coverage {
  course_pages?: number;
  orphan_announcements?: number;
  course_only_assignments?: number;
  forms?: number;
  calendar_items?: number;
  unread_endpoints?: string[];
}

export interface SyncStatus {
  latest: SyncRun | null;
  last_success_at: string | null;
  next_run_at: string | null;
  stale: boolean;
  interval_hours: number;
}

export interface ConnectionStatus {
  connected: boolean;
  nexus_email?: string | null;
  last_login_at: string | null;
  last_error: string | null;
}

export interface Alias {
  id: string;
  alias: string;
  source: "seed" | "learned" | "user";
  weight: number;
}

export interface Mutation<T = WorkItem> {
  item: T;
  undo_token?: string;
}

export interface ItemPatch {
  my_note?: string | null;
  due_at?: string | null;
  due_use_upstream?: boolean;
  title?: string;
  kind?: WorkKind;
  is_hidden?: boolean;
}

export interface NewItem {
  title: string;
  course_id: string | null;
  kind?: WorkKind;
  due_at?: string | null;
  instructions_md?: string | null;
}

export const TASK_KINDS: WorkKind[] = ["assignment", "workbook", "async_assignment", "form", "announcement_task", "exam"];
export const KIND_LABEL: Record<WorkKind, string> = {
  assignment: "Assignment",
  workbook: "Workbook",
  async_assignment: "Async",
  form: "Form",
  announcement_task: "Task",
  exam: "Exam",
  event: "Event",
  info: "Info",
};
export const STATUS_LABEL: Record<MyStatus, string> = {
  pending: "Pending",
  in_progress: "In progress",
  submitted: "Submitted",
  not_applicable: "N/A",
};
