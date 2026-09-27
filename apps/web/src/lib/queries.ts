import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { ApiError, backend } from "./backend";
import { useUI } from "./store";
import type { Course, ItemPatch, MyStatus, NewItem, WorkItem } from "./types";

export const qk = {
  courses: ["courses"] as const,
  items: ["items"] as const,
  detail: (id: string) => ["item-detail", id] as const,
  sync: ["sync-status"] as const,
  runs: ["sync-runs"] as const,
  connection: ["connection"] as const,
  aliases: (id: string) => ["aliases", id] as const,
};

export const useCourses = () => useQuery({ queryKey: qk.courses, queryFn: () => backend().listCourses() });
export const useItems = () => useQuery({ queryKey: qk.items, queryFn: () => backend().listItems() });
export const useItemDetail = (id: string | null) =>
  useQuery({ queryKey: qk.detail(id ?? ""), queryFn: () => backend().getItemDetail(id!), enabled: !!id });
export const useSyncStatus = () =>
  useQuery({ queryKey: qk.sync, queryFn: () => backend().syncStatus(), refetchInterval: 60_000 });
export const useRuns = () => useQuery({ queryKey: qk.runs, queryFn: () => backend().recentRuns(20) });
export const useConnection = () => useQuery({ queryKey: qk.connection, queryFn: () => backend().connectionStatus() });
export const useAliases = (courseId: string) =>
  useQuery({ queryKey: qk.aliases(courseId), queryFn: () => backend().listAliases(courseId) });

/** Realtime → cache. Invalidations are debounced so a burst of scraper writes causes one refetch. */
export function useRealtime() {
  const qc = useQueryClient();
  useEffect(() => {
    const timers = new Map<string, number>();
    const bump = (keys: readonly (readonly unknown[])[]) => {
      const id = JSON.stringify(keys);
      window.clearTimeout(timers.get(id));
      timers.set(id, window.setTimeout(() => keys.forEach((k) => qc.invalidateQueries({ queryKey: k })), 300));
    };
    return backend().subscribe((topic) => {
      if (topic === "work_items") bump([qk.items]);
      if (topic === "courses") bump([qk.courses]);
      if (topic === "sync_runs") bump([qk.sync, qk.runs, qk.connection]);
    });
  }, [qc]);
}

function patchCache(qc: QueryClient, id: string, fn: (w: WorkItem) => WorkItem) {
  const prev = qc.getQueryData<WorkItem[]>(qk.items);
  qc.setQueryData<WorkItem[]>(qk.items, (old) => old?.map((w) => (w.id === id ? fn(w) : w)));
  return prev;
}
function putItem(qc: QueryClient, item: WorkItem) {
  qc.setQueryData<WorkItem[]>(qk.items, (old) =>
    old ? (old.some((w) => w.id === item.id) ? old.map((w) => (w.id === item.id ? item : w)) : [...old, item]) : [item],
  );
  void qc.invalidateQueries({ queryKey: qk.detail(item.id) });
}

const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong — try again.");

/** Undo toast + ⌘Z wiring shared by every undoable mutation. */
function useUndoToast() {
  const qc = useQueryClient();
  const { toast, setLastUndo, dismissToast } = useUI.getState();
  return (title: string, token?: string) => {
    if (!token) {
      toast({ title });
      return;
    }
    let toastId = 0;
    const run = async () => {
      setLastUndo(null);
      dismissToast(toastId);
      try {
        const { items } = await backend().undo(token);
        items.forEach((w) => putItem(qc, w));
        toast({ title: "Undone" });
      } catch (e) {
        toast({ title: "Couldn't undo", description: errMsg(e), tone: "danger" });
      }
    };
    setLastUndo(run);
    toastId = toast({ title, action: { label: "Undo", onClick: run }, duration: 5000 });
  };
}

export function useMoveItem() {
  const qc = useQueryClient();
  const undoToast = useUndoToast();
  return useMutation({
    mutationFn: ({ id, courseId }: { id: string; courseId: string | null; label: string }) =>
      backend().moveItem(id, courseId),
    onMutate: async ({ id, courseId }) => {
      await qc.cancelQueries({ queryKey: qk.items });
      return { prev: patchCache(qc, id, (w) => ({ ...w, course_id: courseId, classification: "manual" })) };
    },
    onError: (e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(qk.items, ctx.prev);
      useUI.getState().toast({ title: "Move failed — card returned", description: errMsg(e), tone: "danger" });
    },
    onSuccess: (res, v) => {
      putItem(qc, res.item);
      undoToast(`Moved to ${v.label}`, res.undo_token);
    },
  });
}

export function useSetStatus() {
  const qc = useQueryClient();
  const undoToast = useUndoToast();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: MyStatus }) => backend().setStatus(id, status),
    onMutate: async ({ id, status }) => {
      await qc.cancelQueries({ queryKey: qk.items });
      return { prev: patchCache(qc, id, (w) => ({ ...w, my_status: status, my_status_set_by: "user" })) };
    },
    onError: (e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(qk.items, ctx.prev);
      useUI.getState().toast({ title: "Couldn't update status", description: errMsg(e), tone: "danger" });
    },
    onSuccess: (res, v) => {
      putItem(qc, res.item);
      if (v.status === "submitted") undoToast("Marked submitted", res.undo_token);
    },
  });
}

export function usePatchItem(opts: { quiet?: boolean } = {}) {
  const qc = useQueryClient();
  const undoToast = useUndoToast();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: ItemPatch }) => backend().patchItem(id, patch),
    onMutate: async ({ id, patch }) => {
      await qc.cancelQueries({ queryKey: qk.items });
      const rest: ItemPatch = { ...patch };
      delete rest.due_use_upstream;
      return { prev: patchCache(qc, id, (w) => ({ ...w, ...rest }) as WorkItem) };
    },
    onError: (e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(qk.items, ctx.prev);
      useUI.getState().toast({ title: "Couldn't save", description: errMsg(e), tone: "danger" });
    },
    onSuccess: (res, v) => {
      putItem(qc, res.item);
      if (opts.quiet) return;
      if (v.patch.is_hidden) undoToast("Hidden", res.undo_token);
      else if (v.patch.due_at !== undefined || v.patch.due_use_upstream) undoToast("Due date updated", res.undo_token);
    },
  });
}

export function useCreateItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (n: NewItem) => backend().createItem(n),
    onSuccess: (res) => {
      putItem(qc, res.item);
      useUI.getState().toast({ title: "Item added" });
    },
    onError: (e) => useUI.getState().toast({ title: "Couldn't add item", description: errMsg(e), tone: "danger" }),
  });
}

export function useMergeItems() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ keepId, mergeId }: { keepId: string; mergeId: string }) => backend().mergeItems(keepId, mergeId),
    onSuccess: (res, v) => {
      qc.setQueryData<WorkItem[]>(qk.items, (old) => old?.filter((w) => w.id !== v.mergeId));
      putItem(qc, res.item);
      useUI.getState().toast({ title: "Merged" });
    },
    onError: (e) => useUI.getState().toast({ title: "Couldn't merge", description: errMsg(e), tone: "danger" }),
  });
}

export function useSyncNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => backend().syncNow(),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.sync });
      useUI.getState().toast({ title: "Sync started", description: "Items update live as Nexus is read." });
    },
    onError: (e) =>
      useUI.getState().toast({
        title: e instanceof ApiError && e.status === 429 ? "Synced recently" : "Couldn't start sync",
        description: errMsg(e),
        tone: e instanceof ApiError && e.status === 429 ? "default" : "danger",
      }),
  });
}

export function usePatchCourse() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<Pick<Course, "short_name" | "color_index" | "is_archived">> }) =>
      backend().patchCourse(id, patch),
    onMutate: async ({ id, patch }) => {
      const prev = qc.getQueryData<Course[]>(qk.courses);
      qc.setQueryData<Course[]>(qk.courses, (old) => old?.map((c) => (c.id === id ? { ...c, ...patch } : c)));
      return { prev };
    },
    onError: (e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(qk.courses, ctx.prev);
      useUI.getState().toast({ title: "Couldn't update course", description: errMsg(e), tone: "danger" });
    },
  });
}
