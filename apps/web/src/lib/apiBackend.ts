import { ApiError, type Backend, type ChangeTopic } from "./backend";
import type {
  Alias,
  ConnectionStatus,
  Course,
  ItemDetail,
  ItemPatch,
  MyStatus,
  Mutation,
  NewItem,
  SyncRun,
  SyncStatus,
  WorkItem,
} from "./types";

const TOKEN_KEY = "ez.session";

function readToken(): { token: string; email: string } | null {
  try {
    const raw = localStorage.getItem(TOKEN_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as { token: string; email: string };
    // drop expired sessions client-side too (the API is the real check)
    const payload = JSON.parse(atob(s.token.split(".")[1]!.replace(/-/g, "+").replace(/_/g, "/"))) as { exp?: number };
    if (payload.exp && payload.exp * 1000 < Date.now()) return null;
    return s;
  } catch {
    return null;
  }
}

/** Everything goes through the EZTracker API (MongoDB never talks to the browser). */
export class ApiBackend implements Backend {
  readonly mode = "live" as const;
  private session = readToken();
  private authListeners = new Set<(email: string | null) => void>();

  constructor(private api: string) {}

  // ------------------------------------------------------------------ session
  async getSessionEmail() {
    if (!this.session) return null;
    try {
      await this.call("GET", "/api/auth/me");
      return this.session.email;
    } catch {
      return null; // expired or revoked → sign-in screen
    }
  }
  async signIn(email: string, password: string) {
    const r = await this.call<{ token: string; email: string }>("POST", "/api/auth/login", { email, password }, false);
    this.session = r;
    try {
      localStorage.setItem(TOKEN_KEY, JSON.stringify(r));
    } catch {
      /* private mode: session lasts for this tab */
    }
    this.authListeners.forEach((l) => l(r.email));
  }
  async signInWithEmail() {
    throw new ApiError(400, "Use email and password");
  }
  async signOut() {
    this.session = null;
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
    this.authListeners.forEach((l) => l(null));
  }
  onAuthChange(cb: (email: string | null) => void) {
    this.authListeners.add(cb);
    return () => this.authListeners.delete(cb);
  }

  private async call<T>(method: string, path: string, body?: unknown, auth = true): Promise<T> {
    const res = await fetch(this.api + path, {
      method,
      headers: {
        "content-type": "application/json",
        ...(auth && this.session ? { authorization: `Bearer ${this.session.token}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 401 && auth && this.session) {
      void this.signOut();
    }
    if (!res.ok) {
      let msg = res.statusText;
      try {
        const p = await res.json();
        msg = typeof p.detail === "string" ? p.detail : p.title || msg;
      } catch {
        /* not JSON */
      }
      throw new ApiError(res.status, msg);
    }
    if (res.status === 204) return undefined as T;
    const ctype = res.headers.get("content-type") || "";
    return (ctype.includes("json") ? res.json() : res.blob()) as Promise<T>;
  }

  // ------------------------------------------------------------------ reads
  listCourses() {
    return this.call<Course[]>("GET", "/api/courses");
  }
  listItems() {
    return this.call<WorkItem[]>("GET", "/api/items");
  }
  getItemDetail(id: string) {
    return this.call<ItemDetail>("GET", `/api/items/${id}/detail`);
  }
  searchItems(q: string) {
    return this.call<WorkItem[]>("GET", `/api/items/search?q=${encodeURIComponent(q)}`);
  }
  syncStatus() {
    return this.call<SyncStatus>("GET", "/api/sync/status");
  }
  recentRuns() {
    return this.call<SyncRun[]>("GET", "/api/sync/runs");
  }
  connectionStatus() {
    return this.call<ConnectionStatus>("GET", "/api/credentials");
  }
  listAliases(courseId: string) {
    return this.call<Alias[]>("GET", `/api/courses/${courseId}/aliases`);
  }
  async calendarUrl() {
    const { path } = await this.call<{ path: string }>("GET", "/api/settings/calendar");
    return this.api + path;
  }

  // ------------------------------------------------------------------ writes
  moveItem(id: string, courseId: string | null) {
    return this.call<Mutation>("PATCH", `/api/items/${id}/move`, { course_id: courseId });
  }
  setStatus(id: string, status: MyStatus) {
    return this.call<Mutation>("PATCH", `/api/items/${id}/status`, { my_status: status });
  }
  patchItem(id: string, patch: ItemPatch) {
    return this.call<Mutation>("PATCH", `/api/items/${id}`, patch);
  }
  createItem(item: NewItem) {
    return this.call<Mutation>("POST", "/api/items", item);
  }
  undo(token: string) {
    return this.call<{ items: WorkItem[] }>("POST", "/api/items/undo", { undo_token: token });
  }
  mergeItems(keepId: string, mergeId: string) {
    return this.call<Mutation>("POST", "/api/items/merge", { keep_id: keepId, merge_id: mergeId });
  }
  syncNow() {
    return this.call<{ run_id: string }>("POST", "/api/sync");
  }
  connect(email: string, password: string) {
    return this.call<ConnectionStatus>("POST", "/api/credentials", { email, password });
  }
  async disconnect() {
    await this.call("DELETE", "/api/credentials");
  }
  patchCourse(id: string, patch: Partial<Pick<Course, "short_name" | "color_index" | "is_archived">>) {
    return this.call<Course>("PATCH", `/api/courses/${id}`, patch);
  }
  addAlias(courseId: string, alias: string) {
    return this.call<Alias>("POST", `/api/courses/${courseId}/aliases`, { alias });
  }
  async deleteAlias(courseId: string, aliasId: string) {
    await this.call("DELETE", `/api/courses/${courseId}/aliases/${aliasId}`);
  }
  exportData(format: "json" | "csv") {
    return this.call<Blob>("GET", `/api/export?format=${format}`);
  }

  // ------------------------------------------------------------------ live updates (SSE ← Mongo change streams)
  subscribe(cb: (topic: ChangeTopic) => void) {
    let es: EventSource | null = null;
    let poll: number | undefined;
    let closed = false;
    const startPolling = () => {
      if (poll) return;
      poll = window.setInterval(() => {
        cb("work_items");
        cb("sync_runs");
      }, 30_000);
    };
    const open = () => {
      if (closed || !this.session) return;
      es = new EventSource(`${this.api}/api/stream?token=${encodeURIComponent(this.session.token)}`);
      es.onmessage = (e) => {
        try {
          const { topic } = JSON.parse(e.data) as { topic: ChangeTopic };
          cb(topic);
        } catch {
          /* ignore malformed */
        }
      };
      es.addEventListener("degraded", () => {
        es?.close();
        startPolling(); // change streams unavailable → refresh every 30s instead
      });
    };
    open();
    return () => {
      closed = true;
      es?.close();
      if (poll) window.clearInterval(poll);
    };
  }
}
