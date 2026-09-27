/**
 * Data access seam. Everything goes through the EZTracker API (FastAPI + MongoDB Atlas); the browser never
 * talks to the database. When no API URL is configured (or `?demo` is in the URL), a local demo backend with
 * fixture data stands in so the UI can be developed, tested and shown without any infrastructure.
 */
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

export type ChangeTopic = "work_items" | "sync_runs" | "courses";

export interface Backend {
  readonly mode: "live" | "demo";
  // session
  getSessionEmail(): Promise<string | null>;
  signIn(email: string, password: string): Promise<void>;
  signInWithEmail(email: string): Promise<void>;
  signOut(): Promise<void>;
  onAuthChange(cb: (email: string | null) => void): () => void;
  // reads
  listCourses(): Promise<Course[]>;
  listItems(): Promise<WorkItem[]>;
  getItemDetail(id: string): Promise<ItemDetail>;
  searchItems(q: string): Promise<WorkItem[]>;
  syncStatus(): Promise<SyncStatus>;
  recentRuns(limit?: number): Promise<SyncRun[]>;
  connectionStatus(): Promise<ConnectionStatus>;
  listAliases(courseId: string): Promise<Alias[]>;
  calendarUrl(): Promise<string>;
  // writes
  moveItem(id: string, courseId: string | null): Promise<Mutation>;
  setStatus(id: string, status: MyStatus): Promise<Mutation>;
  patchItem(id: string, patch: ItemPatch): Promise<Mutation>;
  createItem(item: NewItem): Promise<Mutation>;
  undo(token: string): Promise<{ items: WorkItem[] }>;
  mergeItems(keepId: string, mergeId: string): Promise<Mutation>;
  syncNow(): Promise<{ run_id: string }>;
  connect(email: string, password: string): Promise<ConnectionStatus>;
  disconnect(): Promise<void>;
  patchCourse(id: string, patch: Partial<Pick<Course, "short_name" | "color_index" | "is_archived">>): Promise<Course>;
  addAlias(courseId: string, alias: string): Promise<Alias>;
  deleteAlias(courseId: string, aliasId: string): Promise<void>;
  exportData(format: "json" | "csv"): Promise<Blob>;
  // realtime
  subscribe(cb: (topic: ChangeTopic) => void): () => void;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let instance: Backend | null = null;

export async function getBackend(): Promise<Backend> {
  if (instance) return instance;
  const api = import.meta.env.VITE_API_URL as string | undefined;
  const params = new URLSearchParams(location.search);
  let forceDemo = params.has("demo");
  try {
    if (forceDemo) sessionStorage.setItem("ez.forceDemo", "1");
    forceDemo = forceDemo || sessionStorage.getItem("ez.forceDemo") === "1";
  } catch {
    /* storage unavailable */
  }
  if (api && !forceDemo) {
    const { ApiBackend } = await import("./apiBackend");
    instance = new ApiBackend(api.replace(/\/$/, ""));
  } else {
    const { DemoBackend } = await import("./demoBackend");
    instance = new DemoBackend();
  }
  return instance;
}

/** synchronous accessor once bootstrapped (see app/providers.tsx) */
export function backend(): Backend {
  if (!instance) throw new Error("backend not initialised");
  return instance;
}
