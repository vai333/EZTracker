import { AlertTriangle, CircleAlert, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { Button, Tip } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { formatTime, sinceLabel } from "@/lib/dates";
import { useSyncNow, useSyncStatus } from "@/lib/queries";

export function SyncChip({ collapsed }: { collapsed?: boolean }) {
  const { data } = useSyncStatus();
  if (!data) return null;
  const running = data.latest?.status === "running";
  const failed = data.latest?.status === "failed";
  const label = running
    ? "Syncing…"
    : failed
      ? "Sync failed — view"
      : data.stale
        ? "Stale"
        : `Synced ${sinceLabel(data.last_success_at)}${data.next_run_at ? ` · next ${formatTime(data.next_run_at)}` : ""}`;
  const tone = failed ? "danger" : data.stale ? "warning" : "ok";
  const chip = (
    <Link
      to="/settings#sync"
      className={cn(
        "flex min-h-10 items-center gap-2 rounded-lg px-3 py-2 text-small transition-colors hover:bg-surface-2",
        tone === "danger" && "text-danger-text",
        tone === "warning" && "text-warning-text",
        tone === "ok" && "text-muted",
        collapsed && "justify-center px-0",
      )}
    >
      {failed ? <CircleAlert size={16} strokeWidth={1.5} /> : data.stale ? <AlertTriangle size={16} strokeWidth={1.5} /> : (
        <RefreshCw size={16} strokeWidth={1.5} className={cn(running && "animate-spin")} />
      )}
      {!collapsed && <span className="truncate">{label}</span>}
      {collapsed && <span className="sr-only">{label}</span>}
    </Link>
  );
  return collapsed ? <Tip content={label} side="right">{chip}</Tip> : chip;
}

export function SyncNowButton() {
  const sync = useSyncNow();
  const { data } = useSyncStatus();
  const running = sync.isPending || data?.latest?.status === "running";
  return (
    <Tip content="Sync now">
      <Button variant="ghost" size="icon" aria-label="Sync now" onClick={() => sync.mutate()} disabled={running}>
        <RefreshCw size={18} strokeWidth={1.5} className={cn(running && "animate-spin")} />
      </Button>
    </Tip>
  );
}

export function StaleBanner() {
  const { data } = useSyncStatus();
  const sync = useSyncNow();
  if (!data?.stale || data.latest?.status === "running") return null;
  return (
    <div role="status" className="mx-4 mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-warning px-4 py-2.5 text-small md:mx-6">
      <AlertTriangle size={16} strokeWidth={1.5} className="text-warning" />
      <span className="flex-1 text-text">
        Data may be out of date — last successful sync {sinceLabel(data.last_success_at)}.
      </span>
      <Button size="sm" onClick={() => sync.mutate()} disabled={sync.isPending}>Sync now</Button>
    </div>
  );
}

export function OfflineBanner({ online }: { online: boolean }) {
  if (online) return null;
  return (
    <div role="status" className="mx-4 mt-3 rounded-xl border border-border bg-surface-2 px-4 py-2.5 text-small text-muted md:mx-6">
      You're offline — showing the last loaded data. Changes are disabled until you reconnect.
    </div>
  );
}
