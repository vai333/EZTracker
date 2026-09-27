/**
 * Offline demo backend. Seeded from demo-data.json (produced by the real Python pipeline) with dates
 * shifted to "now", persisted in localStorage. Mirrors the server's rules closely enough for UI work
 * and E2E tests: moves become manual and learn aliases, user status is sticky, undo restores snapshots.
 * It never stores a Nexus password — `connect` only records that a connection was made.
 */
import type { Backend, ChangeTopic } from "./backend";
import { ApiError } from "./backend";
import raw from "./demo-data.json";
import type {
  Alias,
  ConnectionStatus,
  Course,
  ItemDetail,
  ItemEvent,
  ItemPatch,
  MyStatus,
  Mutation,
  NewItem,
  SourceNotification,
  SyncRun,
  SyncStatus,
  WorkItem,
} from "./types";

const KEY = "ez.demo.v2";
const STOP = new Set(
  "a an and are as at be by for from has have in is it its of on or the to with your you new session important update reminder panel clubs leaderboard assignment workbook form group".split(" "),
);

interface DemoAlias extends Alias {
  course_id: string;
}
interface DB {
  courses: Course[];
  items: WorkItem[];
  aliases: DemoAlias[];
  notifications: SourceNotification[];
  sources: [string, string][];
  events: (ItemEvent & { work_item_id: string; undo_token?: string })[];
  runs: SyncRun[];
  connected: ConnectionStatus;
  undo: Record<string, { at: number; before: WorkItem[]; aliasesBefore: DemoAlias[] }>;
  calendarToken: string;
}

const uid = () => (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now());
const now = () => new Date().toISOString();

function shift(iso: string | null, offset: number): string | null {
  return iso ? new Date(new Date(iso).getTime() + offset).toISOString() : null;
}

function freshDB(): DB {
  const offset = Date.now() - new Date(raw.generated_for).getTime();
  const items = (raw.work_items as unknown as WorkItem[]).map((w) => ({
    ...w,
    due_at: shift(w.due_at, offset),
    first_seen_at: shift(w.first_seen_at, offset)!,
    updated_at: shift(w.updated_at, offset)!,
  }));
  return {
    courses: raw.courses as unknown as Course[],
    items,
    aliases: (raw.aliases as unknown as DemoAlias[]).map((a) => ({ ...a })),
    notifications: (raw.notifications as unknown as SourceNotification[]).map((n) => ({
      ...n,
      published_at: shift(n.published_at, offset),
    })),
    sources: raw.sources as [string, string][],
    events: items.map((w, i) => ({
      id: i + 1, work_item_id: w.id, actor: "scraper", event: "created", from_value: null,
      to_value: { title: w.title }, created_at: w.first_seen_at,
    })),
    runs: [{
      id: uid(), trigger: "schedule", status: "success", started_at: new Date(Date.now() - 12 * 60000).toISOString(),
      finished_at: new Date(Date.now() - 11 * 60000).toISOString(),
      stats: { courses: 9, assignments_new: 5, notifications_new: 8, changed: 0, needs_review: 3, coverage: { course_pages: 9, orphan_announcements: 0, course_only_assignments: 0, forms: 0, calendar_items: 0, unread_endpoints: [] } }, surface_errors: [],
    }],
    connected: { connected: true, nexus_email: "demo@mesaschool.co", last_login_at: now(), last_error: null },
    undo: {},
    calendarToken: uid().replace(/-/g, ""),
  };
}

export class DemoBackend implements Backend {
  readonly mode = "demo" as const;
  private db: DB;
  private listeners = new Set<(t: ChangeTopic) => void>();

  constructor() {
    let loaded: DB | null = null;
    try {
      const s = localStorage.getItem(KEY);
      if (s) loaded = JSON.parse(s) as DB;
    } catch {
      loaded = null;
    }
    this.db = loaded ?? freshDB();
  }

  static reset() {
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* storage unavailable */
    }
  }

  private save(topic: ChangeTopic = "work_items") {
    try {
      localStorage.setItem(KEY, JSON.stringify(this.db));
    } catch {
      /* private mode: keep in memory */
    }
    queueMicrotask(() => this.listeners.forEach((l) => l(topic)));
  }
  private latency<T>(v: T, ms = 120): Promise<T> {
    return new Promise((r) => setTimeout(() => r(structuredClone(v)), ms));
  }
  private item(id: string): WorkItem {
    const w = this.db.items.find((x) => x.id === id);
    if (!w) throw new ApiError(404, "item not found");
    return w;
  }
  private event(w: WorkItem, event: string, from: unknown, to: unknown, token?: string) {
    this.db.events.push({
      id: this.db.events.length + 1, work_item_id: w.id, actor: "user", event, from_value: from, to_value: to,
      created_at: now(), undo_token: token,
    });
  }
  private snapshot(ids: string[]): string {
    const token = uid();
    this.db.undo[token] = {
      at: Date.now(),
      before: this.db.items.filter((w) => ids.includes(w.id)).map((w) => ({ ...w })),
      aliasesBefore: this.db.aliases.map((a) => ({ ...a })),
    };
    return token;
  }

  // session: demo is always "signed in"
  async getSessionEmail() { return "demo@eztracker.local"; }
  async signIn() {}
  async signInWithEmail() {}
  async signOut() { DemoBackend.reset(); location.reload(); }
  onAuthChange() { return () => {}; }

  listCourses() { return this.latency(this.db.courses); }
  listItems() { return this.latency(this.db.items); }
  getItemDetail(id: string): Promise<ItemDetail> {
    const nids = this.db.sources.filter(([w]) => w === id).map(([, n]) => n);
    return this.latency({
      sources: this.db.notifications.filter((n) => nids.includes(n.id)),
      events: this.db.events.filter((e) => e.work_item_id === id).slice().reverse(),
    });
  }
  searchItems(q: string) {
    const t = q.toLowerCase().trim();
    return this.latency(this.db.items.filter((w) => `${w.title} ${w.instructions_md ?? ""}`.toLowerCase().includes(t)).slice(0, 20), 60);
  }
  syncStatus(): Promise<SyncStatus> {
    const latest = this.db.runs[0] ?? null;
    const ok = this.db.runs.find((r) => r.status === "success" || r.status === "partial");
    const last = ok?.finished_at ?? null;
    const next = new Date((last ? new Date(last).getTime() : Date.now()) + 3 * 3600_000).toISOString();
    return this.latency({ latest, last_success_at: last, next_run_at: next, interval_hours: 3,
      stale: !last || Date.now() - new Date(last).getTime() > 7 * 3600_000 }, 60);
  }
  recentRuns(limit = 20) { return this.latency(this.db.runs.slice(0, limit)); }
  connectionStatus() { return this.latency(this.db.connected); }
  listAliases(courseId: string) { return this.latency(this.db.aliases.filter((a) => a.course_id === courseId)); }
  async calendarUrl() { return `${location.origin}/api/calendar.ics?token=${this.db.calendarToken}`; }

  async moveItem(id: string, courseId: string | null): Promise<Mutation> {
    const w = this.item(id);
    const token = this.snapshot([id]);
    const from = { course_id: w.course_id, classification: w.classification };
    if (courseId && w.course_id !== courseId) {
      const known = new Set(this.db.aliases.filter((a) => a.course_id === courseId).map((a) => a.alias));
      w.title.toLowerCase().replace(/[^\w\s]/g, " ").split(/\s+/)
        .filter((t) => t.length > 2 && !STOP.has(t) && !/^\d+$/.test(t) && !known.has(t)).slice(0, 3)
        .forEach((alias) => this.db.aliases.push({ id: uid(), course_id: courseId, alias, source: "learned", weight: 0.5 }));
    }
    Object.assign(w, { course_id: courseId, classification: "manual", confidence: courseId ? 1 : w.confidence, updated_at: now() });
    this.event(w, "moved", from, { course_id: courseId }, token);
    this.save();
    return this.latency({ item: w, undo_token: token }, 200);
  }
  async setStatus(id: string, status: MyStatus): Promise<Mutation> {
    const w = this.item(id);
    const token = this.snapshot([id]);
    const from = { my_status: w.my_status };
    Object.assign(w, { my_status: status, my_status_set_by: "user", updated_at: now() });
    this.event(w, "status_changed", from, { my_status: status }, token);
    this.save();
    return this.latency({ item: w, undo_token: token });
  }
  async patchItem(id: string, p: ItemPatch): Promise<Mutation> {
    const w = this.item(id);
    const token = this.snapshot([id]);
    const before = { ...w };
    if (p.my_note !== undefined) w.my_note = p.my_note;
    if (p.title) Object.assign(w, { title: p.title });
    if (p.kind) w.kind = p.kind;
    if (p.is_hidden !== undefined) w.is_hidden = p.is_hidden;
    if (p.due_use_upstream) Object.assign(w, { due_at: w.upstream_due_at, due_source: "nexus_field", upstream_due_at: null });
    else if (p.due_at !== undefined) Object.assign(w, { due_at: p.due_at, due_source: "user" });
    w.updated_at = now();
    const changed = Object.keys(p).filter((k) => k !== "due_use_upstream");
    this.event(w, changed.length === 1 && changed[0] === "is_hidden" ? "hidden" : changed.includes("due_at") ? "due_changed" : "edited",
      Object.fromEntries(changed.map((k) => [k, (before as unknown as Record<string, unknown>)[k]])), p, token);
    this.save();
    return this.latency({ item: w, undo_token: token });
  }
  async createItem(n: NewItem): Promise<Mutation> {
    const w: WorkItem = {
      id: uid(), course_id: n.course_id, title: n.title, kind: n.kind ?? "assignment", origin: "manual",
      due_at: n.due_at ?? null, due_source: n.due_at ? "user" : null, instructions_md: n.instructions_md ?? null,
      links: [], nexus_status: null, my_status: "pending", my_status_set_by: "default", my_note: null,
      classification: "manual", confidence: 1, classifier_reasons: [], is_hidden: false, upstream_due_at: null,
      due_changed_at: null, upstream_updated_at: null, first_seen_at: now(), updated_at: now(),
    };
    this.db.items.push(w);
    this.event(w, "created", null, { title: w.title });
    this.save();
    return this.latency({ item: w });
  }
  async undo(token: string) {
    const u = this.db.undo[token];
    if (!u || Date.now() - u.at > 30_000) throw new ApiError(410, "nothing to undo (token expired or unknown)");
    delete this.db.undo[token];
    for (const b of u.before) {
      const i = this.db.items.findIndex((w) => w.id === b.id);
      if (i >= 0) this.db.items[i] = b;
      this.event(b, "undo", null, null);
    }
    this.db.aliases = u.aliasesBefore;
    this.save();
    return this.latency({ items: u.before });
  }
  async mergeItems(keepId: string, mergeId: string): Promise<Mutation> {
    const keep = this.item(keepId);
    const gone = this.item(mergeId);
    if (keep.origin !== "notification_only" && keep.origin !== "manual" && gone.origin !== "notification_only" && gone.origin !== "manual")
      throw new ApiError(409, "both items are Nexus assignments; they cannot be merged");
    this.db.sources = this.db.sources.map(([w, n]) => [w === mergeId ? keepId : w, n] as [string, string]);
    if (!keep.due_at && gone.due_at) Object.assign(keep, { due_at: gone.due_at, due_source: gone.due_source });
    if (gone.my_note) keep.my_note = [keep.my_note, gone.my_note].filter(Boolean).join("\n\n");
    this.db.items = this.db.items.filter((w) => w.id !== mergeId);
    this.event(keep, "merged", null, { merged_from: { id: gone.id, title: gone.title } });
    this.save();
    return this.latency({ item: keep });
  }
  async syncNow() {
    const last = this.db.runs[0];
    if (last && Date.now() - new Date(last.started_at).getTime() < 10 * 60_000 && last.trigger === "manual")
      throw new ApiError(429, "last sync started less than 10 min ago");
    const run: SyncRun = { id: uid(), trigger: "manual", status: "running", started_at: now(), finished_at: null, stats: {}, surface_errors: [] };
    this.db.runs.unshift(run);
    this.save("sync_runs");
    setTimeout(() => {
      Object.assign(run, { status: "success", finished_at: now(), stats: { courses: 9, assignments_new: 0, notifications_new: 0, changed: 0, needs_review: 0 } });
      this.db.runs[0] = run;
      this.save("sync_runs");
    }, 2200);
    return { run_id: run.id };
  }
  async connect(email: string): Promise<ConnectionStatus> {
    await new Promise((r) => setTimeout(r, 900));
    this.db.connected = { connected: true, nexus_email: email, last_login_at: now(), last_error: null };
    this.save("sync_runs");
    return this.db.connected;
  }
  async disconnect() {
    this.db.connected = { connected: false, last_login_at: null, last_error: null };
    this.save("sync_runs");
  }
  async patchCourse(id: string, patch: Partial<Pick<Course, "short_name" | "color_index" | "is_archived">>) {
    const c = this.db.courses.find((x) => x.id === id);
    if (!c) throw new ApiError(404, "course not found");
    Object.assign(c, patch);
    this.save("courses");
    return this.latency(c);
  }
  async addAlias(courseId: string, alias: string) {
    const a: DemoAlias = { id: uid(), course_id: courseId, alias: alias.toLowerCase().trim(), source: "user", weight: 1 };
    this.db.aliases.push(a);
    this.save("courses");
    return this.latency(a);
  }
  async deleteAlias(_courseId: string, aliasId: string) {
    this.db.aliases = this.db.aliases.filter((a) => a.id !== aliasId);
    this.save("courses");
  }
  async exportData(format: "json" | "csv") {
    if (format === "json") return new Blob([JSON.stringify(this.db.items, null, 1)], { type: "application/json" });
    const cols = ["id", "title", "course_id", "kind", "due_at", "my_status"] as const;
    const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    return new Blob([[cols.join(","), ...this.db.items.map((w) => cols.map((c) => esc(w[c])).join(","))].join("\n")], { type: "text/csv" });
  }
  subscribe(cb: (t: ChangeTopic) => void) {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
}
