import * as DialogP from "@radix-ui/react-dialog";
import * as MenuP from "@radix-ui/react-dropdown-menu";
import * as ToastP from "@radix-ui/react-toast";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { useUI } from "@/lib/store";

const EASE = [0.2, 0.8, 0.2, 1] as const;

// ------------------------------------------------------------------ Dialog (centered)

export function Dialog({ open, onOpenChange, title, description, children, className }: {
  open: boolean; onOpenChange: (v: boolean) => void; title: string; description?: string; children: ReactNode; className?: string;
}) {
  return (
    <DialogP.Root open={open} onOpenChange={onOpenChange}>
      <DialogP.Portal>
        <DialogP.Overlay className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[1px]" />
        <DialogP.Content
          className={cn(
            "fixed left-1/2 top-[12vh] z-50 w-[calc(100vw-32px)] max-w-lg -translate-x-1/2 rounded-col border border-border bg-surface p-5 shadow-lift",
            className,
          )}
        >
          <DialogP.Title className="font-display text-h3">{title}</DialogP.Title>
          {description ? (
            <DialogP.Description className="mt-1 text-small text-muted">{description}</DialogP.Description>
          ) : (
            <DialogP.Description className="sr-only">{title}</DialogP.Description>
          )}
          <div className="mt-4">{children}</div>
          <DialogP.Close className="absolute right-3 top-3 grid h-9 w-9 place-items-center rounded-lg text-muted hover:bg-surface-2" aria-label="Close">
            <X size={18} strokeWidth={1.5} />
          </DialogP.Close>
        </DialogP.Content>
      </DialogP.Portal>
    </DialogP.Root>
  );
}

// ------------------------------------------------------------------ Drawer (right side; full-screen sheet on mobile)

/** Drawer content must render a <DrawerTitle> (the visible heading doubles as the accessible name). */
export function Drawer({ open, onOpenChange, children }: { open: boolean; onOpenChange: (v: boolean) => void; children: ReactNode }) {
  const reduce = useReducedMotion();
  return (
    <DialogP.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <DialogP.Portal forceMount>
            <DialogP.Overlay asChild forceMount>
              <motion.div
                className="fixed inset-0 z-40 bg-black/25"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
              />
            </DialogP.Overlay>
            <DialogP.Content asChild forceMount aria-describedby={undefined}>
              <motion.aside
                className="fixed inset-0 z-50 flex flex-col overflow-hidden border-l border-border bg-surface shadow-lift md:inset-y-0 md:left-auto md:right-0 md:w-[480px] md:rounded-l-col"
                initial={reduce ? { opacity: 0 } : { x: 40, opacity: 0 }}
                animate={reduce ? { opacity: 1 } : { x: 0, opacity: 1 }}
                exit={reduce ? { opacity: 0 } : { x: 40, opacity: 0 }}
                transition={{ duration: 0.24, ease: EASE }}
              >
                {children}
              </motion.aside>
            </DialogP.Content>
          </DialogP.Portal>
        )}
      </AnimatePresence>
    </DialogP.Root>
  );
}

export const DrawerClose = DialogP.Close;
export const DrawerTitle = DialogP.Title;

// ------------------------------------------------------------------ Dropdown menu

export const Menu = MenuP.Root;
export const MenuTrigger = MenuP.Trigger;
export function MenuContent({ children, align = "end" }: { children: ReactNode; align?: "start" | "end" }) {
  return (
    <MenuP.Portal>
      <MenuP.Content
        align={align}
        sideOffset={6}
        className="z-50 min-w-[200px] rounded-xl border border-border bg-surface p-1 shadow-lift"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </MenuP.Content>
    </MenuP.Portal>
  );
}
export function MenuItem({ children, onSelect, tone }: { children: ReactNode; onSelect: () => void; tone?: "danger" }) {
  return (
    <MenuP.Item
      onSelect={onSelect}
      className={cn(
        "flex h-9 cursor-pointer select-none items-center gap-2 rounded-lg px-2.5 text-body outline-none data-[highlighted]:bg-surface-2",
        tone === "danger" ? "text-danger-text" : "text-text",
      )}
    >
      {children}
    </MenuP.Item>
  );
}
export const MenuSeparator = () => <MenuP.Separator className="my-1 h-px bg-border" />;
export const MenuLabel = ({ children }: { children: ReactNode }) => (
  <MenuP.Label className="micro px-2.5 py-1.5 text-faint">{children}</MenuP.Label>
);

// ------------------------------------------------------------------ Toaster (bottom-center, 5s, ⌘Z)

export function Toaster() {
  const { toasts, dismissToast } = useUI();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, [contenteditable=true]")) return;
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === "z") {
        const fn = useUI.getState().lastUndo;
        if (fn) {
          e.preventDefault();
          fn();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <ToastP.Provider swipeDirection="down" duration={4000}>
      {toasts.map((t) => (
        <ToastP.Root
          key={t.id}
          duration={t.duration ?? 4000}
          onOpenChange={(o) => {
            if (!o) {
              dismissToast(t.id);
              if (t.action && useUI.getState().lastUndo === t.action.onClick) useUI.getState().setLastUndo(null);
            }
          }}
          className={cn(
            "flex w-full items-center gap-3 rounded-xl border bg-surface px-4 py-3 shadow-lift",
            "data-[state=open]:animate-[ezToastIn_.24s_cubic-bezier(.2,.8,.2,1)] data-[swipe=end]:animate-none",
            t.tone === "danger" ? "border-danger" : "border-border",
          )}
        >
          <div className="min-w-0 flex-1">
            <ToastP.Title className="text-body font-medium text-text">{t.title}</ToastP.Title>
            {t.description && <ToastP.Description className="text-small text-muted">{t.description}</ToastP.Description>}
          </div>
          {t.action && (
            <ToastP.Action altText={`${t.action.label} (⌘Z)`} asChild>
              <button
                onClick={t.action.onClick}
                className="h-8 rounded-lg px-3 text-small font-semibold text-accent-text hover:bg-surface-2"
              >
                {t.action.label}
              </button>
            </ToastP.Action>
          )}
          <ToastP.Close aria-label="Dismiss" className="grid h-8 w-8 place-items-center rounded-lg text-faint hover:bg-surface-2">
            <X size={16} strokeWidth={1.5} />
          </ToastP.Close>
        </ToastP.Root>
      ))}
      <ToastP.Viewport className="fixed bottom-4 left-1/2 z-[60] flex w-[calc(100vw-32px)] max-w-md -translate-x-1/2 flex-col gap-2 outline-none" />
    </ToastP.Provider>
  );
}
