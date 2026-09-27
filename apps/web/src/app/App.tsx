import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as TooltipP from "@radix-ui/react-tooltip";
import { lazy, Suspense, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/overlays";
import { getBackend, type Backend } from "@/lib/backend";
import { applyTheme, useUI } from "@/lib/store";
import { Shell } from "./Shell";
import { AuthGate } from "./AuthGate";
import { Skeleton } from "@/components/ui/primitives";

const AgendaView = lazy(() => import("@/features/agenda/AgendaView"));
const BoardView = lazy(() => import("@/features/board/BoardView"));
const NeedsReviewView = lazy(() => import("@/features/board/NeedsReviewView"));
const CoursesView = lazy(() => import("@/features/courses/CoursesView"));
const SettingsView = lazy(() => import("@/features/settings/SettingsView"));
const Styleguide = lazy(() => import("@/features/styleguide/Styleguide"));

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: true, retry: 1 } },
});

function PageFallback() {
  return (
    <div className="space-y-3 p-6" aria-busy>
      <Skeleton className="h-10 w-64" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}

export function App() {
  const [be, setBe] = useState<Backend | null>(null);
  const theme = useUI((s) => s.theme);
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);
  useEffect(() => {
    void getBackend().then(setBe);
  }, []);
  if (!be) return null;
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipP.Provider>
        <BrowserRouter>
          <AuthGate>
            <Routes>
              <Route element={<Shell />}>
                <Route index element={<Navigate to="/today" replace />} />
                <Route path="/today" element={<Suspense fallback={<PageFallback />}><AgendaView /></Suspense>} />
                <Route path="/board" element={<Suspense fallback={<PageFallback />}><BoardView /></Suspense>} />
                <Route path="/review" element={<Suspense fallback={<PageFallback />}><NeedsReviewView /></Suspense>} />
                <Route path="/courses" element={<Suspense fallback={<PageFallback />}><CoursesView /></Suspense>} />
                <Route path="/settings" element={<Suspense fallback={<PageFallback />}><SettingsView /></Suspense>} />
                <Route path="/styleguide" element={<Suspense fallback={<PageFallback />}><Styleguide /></Suspense>} />
                <Route path="*" element={<Navigate to="/today" replace />} />
              </Route>
            </Routes>
          </AuthGate>
          <Toaster />
        </BrowserRouter>
      </TooltipP.Provider>
    </QueryClientProvider>
  );
}
