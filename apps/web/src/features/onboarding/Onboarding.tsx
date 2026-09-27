import { useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Lock } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Input, Label } from "@/components/ui/primitives";
import { backend } from "@/lib/backend";
import { APP_NAME } from "@/lib/brand";
import { cn } from "@/lib/cn";
import { isNeedsReview } from "@/lib/items";
import { qk } from "@/lib/queries";

const STEPS = [
  { key: "verify", label: "Verifying login" },
  { key: "courses", label: "Reading courses" },
  { key: "assignments", label: "Reading assignments" },
  { key: "notifications", label: "Reading notifications" },
  { key: "sweep", label: "Checking every course page" },
  { key: "sorting", label: "Sorting" },
] as const;
type Step = (typeof STEPS)[number]["key"] | "done";

export default function Onboarding({ onConnecting, onDone }: { onConnecting: () => void; onDone: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState<Step | null>(null);
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();
  const nav = useNavigate();
  const pwRef = useRef<HTMLInputElement>(null);

  // follow the first sync's real phase via realtime (sync_runs.stats.phase)
  useEffect(() => {
    if (!step || step === "verify") return;
    const check = async () => {
      const s = await backend().syncStatus();
      const run = s.latest;
      if (!run) return;
      const phase = String(run.stats?.phase ?? "");
      if (run.status !== "running") setStep("done");
      else if (STEPS.some((x) => x.key === phase)) setStep(phase as Step);
    };
    const unsub = backend().subscribe((t) => t === "sync_runs" && void check());
    const iv = window.setInterval(check, 2500);
    void check();
    return () => {
      unsub();
      window.clearInterval(iv);
    };
  }, [step]);

  useEffect(() => {
    if (step !== "done") return;
    void (async () => {
      await qc.invalidateQueries();
      const items = await backend().listItems();
      const review = items.filter(isNeedsReview).length;
      onDone();
      nav(review > 0 ? "/review?first=1" : "/today", { replace: true });
    })();
  }, [step, qc, nav, onDone]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setStep("verify");
    onConnecting();
    try {
      await backend().connect(email, password);
      setPassword(""); // never keep the password in memory longer than the request
      setStep("courses");
      await qc.invalidateQueries({ queryKey: qk.connection });
      if (backend().mode === "demo") window.setTimeout(() => setStep("done"), 1200);
    } catch (x) {
      setStep(null);
      setError((x as Error).message || "Couldn't connect to Nexus.");
      onDone();
      pwRef.current?.focus();
    }
  };

  const active = step ? STEPS.findIndex((s) => s.key === step) : -1;

  return (
    <main className="grain grid min-h-dvh place-items-center bg-bg px-4 py-10">
      <div className="card relative z-10 w-full max-w-md p-6 sm:p-8">
        <p className="micro text-accent-text">{APP_NAME}</p>
        <h1 className="mt-2 font-display text-h2">Connect your Nexus account</h1>
        <p className="mt-2 text-body text-muted">
          {APP_NAME} reads your courses, My Work and notifications every 3 hours and puts them in one place, sorted by course.
        </p>
        <ul className="mt-4 space-y-1.5 text-small text-muted">
          <li className="flex gap-2"><Lock size={14} className="mt-0.5 shrink-0 text-success" strokeWidth={1.5} />Your password is encrypted on the server and never sent back to this browser.</li>
          <li className="flex gap-2"><Lock size={14} className="mt-0.5 shrink-0 text-success" strokeWidth={1.5} />It's only used to read your own Nexus data — nothing is ever submitted.</li>
          <li className="flex gap-2"><Lock size={14} className="mt-0.5 shrink-0 text-success" strokeWidth={1.5} />Disconnect anytime in Settings; that deletes it.</li>
        </ul>

        {step === null ? (
          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <Label htmlFor="nx-email">Nexus email</Label>
              <Input id="nx-email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="nx-pw">Password</Label>
              <Input id="nx-pw" ref={pwRef} type="password" autoComplete="current-password" required value={password}
                onChange={(e) => setPassword(e.target.value)} aria-invalid={!!error} aria-describedby={error ? "nx-err" : undefined} />
            </div>
            {error && <p id="nx-err" role="alert" className="text-small text-danger-text">{error}</p>}
            <Button variant="primary" className="w-full">Connect Nexus</Button>
            <p className="text-meta text-faint">
              Sign in with Google or a one-time code? Use <code>make connect</code> on your machine instead — see the README.
            </p>
          </form>
        ) : (
          <ol className="mt-6 space-y-3" aria-live="polite">
            {STEPS.map((s, i) => {
              const done = step === "done" || i < active;
              const now = i === active && step !== "done";
              return (
                <li key={s.key} className={cn("flex items-center gap-3 text-body", done ? "text-text" : now ? "text-text" : "text-faint")}>
                  <span className={cn("grid h-6 w-6 place-items-center rounded-full border", done ? "border-success bg-success text-primary-fg" : "border-border")}>
                    {done ? <Check size={13} strokeWidth={2.5} /> : now ? <Loader2 size={13} className="animate-spin text-accent" /> : null}
                  </span>
                  {s.label}
                  {now && <span className="sr-only">in progress</span>}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </main>
  );
}
