import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, Copy, Download, Link2Off, PlugZap } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Button, Input, Label, Pill, Segmented, Skeleton } from "@/components/ui/primitives";
import { Dialog } from "@/components/ui/overlays";
import { backend } from "@/lib/backend";
import { formatAbsolute, sinceLabel } from "@/lib/dates";
import { qk, useConnection, useRuns, useSyncStatus } from "@/lib/queries";
import { useUI } from "@/lib/store";
import type { RunStatus, SyncRun } from "@/lib/types";

const RUN_TONE: Record<RunStatus, "success" | "warning" | "danger" | "neutral"> = {
  success: "success", partial: "warning", failed: "danger", running: "neutral",
};

function Section({ id, title, children }: { id?: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="card p-5">
      <h2 className="font-display text-h3">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function CoverageSummary({ run }: { run: SyncRun | undefined }) {
  const c = run?.stats.coverage;
  if (!c) return null;
  const unread = c.unread_endpoints ?? [];
  return (
    <div className="mt-3 rounded-lg bg-surface-2 px-3 py-2.5 text-small">
      <p className="text-text">
        Last sync checked {c.course_pages ?? 0} course pages and found {c.orphan_announcements ?? 0} announcements
        without a notification, {c.course_only_assignments ?? 0} course-only assignments, {c.forms ?? 0} forms and{" "}
        {c.calendar_items ?? 0} calendar deadlines.
      </p>
      {unread.length > 0 ? (
        <p className="mt-1 text-warning-text">Nexus also returned lists EZTracker doesn't read yet: {unread.join(", ")}</p>
      ) : (
        <p className="mt-1 text-success-text">Every list Nexus returned was read.</p>
      )}
    </div>
  );
}

function ReconnectDialog({ open, onOpenChange, email: initial }: { open: boolean; onOpenChange: (v: boolean) => void; email: string }) {
  const qc = useQueryClient();
  const toast = useUI((s) => s.toast);
  const [email, setEmail] = useState(initial);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Reconnect Nexus" description="Verifies the new login with Nexus before replacing the stored one.">
      <form className="space-y-3" onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setErr(null);
        try {
          await backend().connect(email, password);
          setPassword("");
          onOpenChange(false);
          toast({ title: "Nexus reconnected" });
          await qc.invalidateQueries({ queryKey: qk.connection });
        } catch (x) {
          setErr((x as Error).message);
        } finally {
          setBusy(false);
        }
      }}>
        <div><Label htmlFor="rc-email">Nexus email</Label><Input id="rc-email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div><Label htmlFor="rc-pw">Password</Label><Input id="rc-pw" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        {err && <p role="alert" className="text-small text-danger-text">{err}</p>}
        <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="primary" disabled={busy}>{busy ? "Verifying…" : "Reconnect"}</Button></div>
      </form>
    </Dialog>
  );
}

export default function SettingsView() {
  const conn = useConnection();
  const sync = useSyncStatus();
  const runs = useRuns();
  const qc = useQueryClient();
  const { theme, setTheme, grain, setGrain, density, setDensity, toast } = useUI();
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const cal = useQuery({ queryKey: ["calendar-url"], queryFn: () => backend().calendarUrl() });

  const download = async (format: "json" | "csv") => {
    const blob = await backend().exportData(format);
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), { href: url, download: `eztracker-items.${format}` });
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4 px-4 py-4 md:px-6">
      <Section title="Nexus connection">
        {conn.isLoading ? <Skeleton className="h-10" /> : (
          <div className="flex flex-wrap items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-body">
                {conn.data?.connected ? <>Connected as <strong>{conn.data.nexus_email}</strong></> : "Not connected"}
              </p>
              <p className="text-small text-muted">Last login {sinceLabel(conn.data?.last_login_at ?? null)}</p>
              {conn.data?.last_error && <p role="alert" className="mt-1 text-small text-danger-text">{conn.data.last_error}</p>}
            </div>
            <Button size="sm" onClick={() => setReconnecting(true)}>
              <PlugZap size={15} strokeWidth={1.5} />Reconnect
            </Button>
            <Button size="sm" variant="danger" onClick={() => setConfirmDisconnect(true)}><Link2Off size={15} strokeWidth={1.5} />Disconnect</Button>
          </div>
        )}
        <Dialog open={confirmDisconnect} onOpenChange={setConfirmDisconnect} title="Disconnect Nexus?"
          description="This deletes your encrypted Nexus password and session from EZTracker. Your items stay; syncing stops until you reconnect.">
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setConfirmDisconnect(false)}>Cancel</Button>
            <Button variant="danger" onClick={async () => {
              await backend().disconnect();
              setConfirmDisconnect(false);
              await qc.invalidateQueries({ queryKey: qk.connection });
            }}>Disconnect</Button>
          </div>
        </Dialog>
        <ReconnectDialog open={reconnecting} onOpenChange={setReconnecting} email={conn.data?.nexus_email ?? ""} />
      </Section>

      <Section id="sync" title="Sync">
        <p className="text-small text-muted">
          Every {sync.data?.interval_hours ?? 3} hours, automatically.
          {sync.data?.next_run_at && <> Next run around {formatAbsolute(sync.data.next_run_at)}.</>}
          {" "}Manual "Sync now" is limited to once every 10 minutes.
        </p>
        <CoverageSummary run={runs.data?.find((r) => r.status !== "running")} />
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-small">
            <thead className="text-faint">
              <tr className="border-b border-border">
                <th className="micro py-2 font-semibold">Started</th>
                <th className="micro py-2 font-semibold">Trigger</th>
                <th className="micro py-2 font-semibold">Status</th>
                <th className="micro py-2 font-semibold">New</th>
                <th className="micro py-2 font-semibold">Issues</th>
              </tr>
            </thead>
            <tbody>
              {runs.data?.map((r) => (
                <tr key={r.id} className="border-b border-border align-top last:border-b-0">
                  <td className="py-2 pr-3 text-text">{formatAbsolute(r.started_at)}</td>
                  <td className="py-2 pr-3 text-muted">{r.trigger}</td>
                  <td className="py-2 pr-3"><Pill tone={RUN_TONE[r.status]}>{r.status}</Pill></td>
                  <td className="py-2 pr-3 text-muted">
                    {Number(r.stats.assignments_new ?? 0)} assignments · {Number(r.stats.notifications_new ?? 0)} notifications
                  </td>
                  <td className="py-2 text-muted">
                    {r.surface_errors.length === 0 ? "—" : r.surface_errors.map((e, i) => (
                      <p key={i} className={e.level === "error" ? "text-danger-text" : ""}>{e.surface}: {e.message}</p>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {runs.data?.length === 0 && <p className="py-4 text-small text-faint">No runs yet.</p>}
        </div>
      </Section>

      <Section title="Courses & aliases">
        <p className="text-small text-muted">Short names, colours, archiving and learned aliases live on the <Link className="text-accent-text underline" to="/courses">Courses</Link> page.</p>
      </Section>

      <Section title="Appearance">
        <div className="space-y-4">
          <div><p className="micro mb-2 text-muted">Theme</p>
            <Segmented label="Theme" value={theme} onChange={setTheme}
              options={[{ value: "system", label: "System" }, { value: "light", label: "Ivory & Forest" }, { value: "dark", label: "Obsidian & Champagne" }]} />
          </div>
          <div><p className="micro mb-2 text-muted">Density</p>
            <Segmented label="Density" value={density} onChange={setDensity}
              options={[{ value: "comfortable", label: "Comfortable" }, { value: "compact", label: "Compact" }]} />
          </div>
          <label className="flex items-center gap-3 text-body">
            <input type="checkbox" checked={grain} onChange={(e) => setGrain(e.target.checked)} className="h-4 w-4 accent-[var(--primary)]" />
            Paper grain (light theme)
          </label>
        </div>
      </Section>

      <Section title="Calendar feed">
        <p className="text-small text-muted">Subscribe in Google Calendar (Other calendars → From URL) to see pending deadlines with a 24-hour reminder. Keep this link private.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <code className="min-w-0 flex-1 truncate rounded-lg bg-surface-2 px-3 py-2 text-meta text-muted">{cal.data ?? "…"}</code>
          <Button size="sm" disabled={!cal.data} onClick={() => { void navigator.clipboard.writeText(cal.data!); toast({ title: "Calendar link copied" }); }}>
            <Copy size={15} strokeWidth={1.5} />Copy
          </Button>
          <a className="inline-flex h-8 items-center gap-2 rounded-lg border border-border px-3 text-small hover:bg-surface-2"
            href={cal.data ? `https://calendar.google.com/calendar/r?cid=${encodeURIComponent(cal.data.replace(/^https?:/, "webcal:"))}` : undefined}
            target="_blank" rel="noreferrer noopener"><CalendarPlus size={15} strokeWidth={1.5} />Add to Google</a>
        </div>
      </Section>

      <Section title="Data export">
        <div className="flex gap-2">
          <Button size="sm" onClick={() => download("json")}><Download size={15} strokeWidth={1.5} />JSON</Button>
          <Button size="sm" onClick={() => download("csv")}><Download size={15} strokeWidth={1.5} />CSV</Button>
        </div>
      </Section>
    </div>
  );
}
