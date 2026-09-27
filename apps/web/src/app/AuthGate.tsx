import { useEffect, useState, type ReactNode } from "react";
import { Button, Input, Label } from "@/components/ui/primitives";
import { backend } from "@/lib/backend";
import { APP_NAME } from "@/lib/brand";
import { useConnection } from "@/lib/queries";
import Onboarding from "@/features/onboarding/Onboarding";

/** Supabase session → Nexus connection → app. Demo mode is always signed in. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [email, setEmail] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    void backend().getSessionEmail().then(setEmail);
    return backend().onAuthChange(setEmail);
  }, []);
  if (email === undefined) return null;
  if (!email) return <SignIn />;
  return <NexusGate>{children}</NexusGate>;
}

function NexusGate({ children }: { children: ReactNode }) {
  const conn = useConnection();
  const [justConnected, setJustConnected] = useState(false);
  if (conn.isLoading) return null;
  if (!conn.data?.connected || justConnected)
    return <Onboarding onConnecting={() => setJustConnected(true)} onDone={() => setJustConnected(false)} />;
  return <>{children}</>;
}

function SignIn() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  return (
    <main className="grid min-h-dvh place-items-center bg-bg px-4">
      <form
        className="card w-full max-w-sm p-6"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setErr("");
          try {
            await backend().signIn(email, password);
            setPassword("");
          } catch (x) {
            setErr((x as Error).message || "Couldn't sign in.");
          } finally {
            setBusy(false);
          }
        }}
      >
        <h1 className="font-display text-h2">{APP_NAME}</h1>
        <p className="mt-1 text-small text-muted">Sign in with your EZTracker owner account.</p>
        <div className="mt-5 space-y-3">
          <div>
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" required autoComplete="current-password" value={password}
              onChange={(e) => setPassword(e.target.value)} aria-invalid={!!err} aria-describedby={err ? "signin-err" : undefined} />
          </div>
        </div>
        <Button variant="primary" className="mt-4 w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
        <p id="signin-err" role="alert" className="mt-3 min-h-5 text-small text-danger-text">{err}</p>
        <p className="text-meta text-faint">No account yet? Create it once with <code>make create-user</code>.</p>
      </form>
    </main>
  );
}
