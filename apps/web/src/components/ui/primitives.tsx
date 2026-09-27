import * as TooltipP from "@radix-ui/react-tooltip";
import { Check, Circle, CircleDot, Minus } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import type { MyStatus } from "@/lib/types";

// ------------------------------------------------------------------ Button

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "icon";

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }>(
  function Button({ variant = "secondary", size = "md", className, ...p }, ref) {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-lg font-medium",
          "transition-[background,color,box-shadow,transform] duration-press ease-ez active:scale-[.98]",
          "disabled:pointer-events-none disabled:opacity-50",
          size === "sm" && "h-8 px-3 text-small",
          size === "md" && "h-10 px-4 text-body",
          size === "icon" && "h-10 w-10 text-body",
          variant === "primary" && "bg-primary text-primary-fg hover:brightness-110",
          variant === "secondary" && "border border-border bg-surface text-text hover:bg-surface-2",
          variant === "ghost" && "text-muted hover:bg-surface-2 hover:text-text",
          variant === "danger" && "border border-border bg-surface text-danger-text hover:bg-surface-2",
          className,
        )}
        {...p}
      />
    );
  },
);

// ------------------------------------------------------------------ Inputs

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...p }, ref) {
  return (
    <input
      ref={ref}
      className={cn(
        "h-10 w-full rounded-lg border border-border bg-surface px-3 text-body text-text placeholder:text-faint",
        "transition-shadow duration-press focus-visible:shadow-focus",
        className,
      )}
      {...p}
    />
  );
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...p }, ref) {
  return (
    <textarea
      ref={ref}
      className={cn(
        "min-h-[88px] w-full resize-y rounded-lg border border-border bg-surface px-3 py-2 text-body text-text placeholder:text-faint focus-visible:shadow-focus",
        className,
      )}
      {...p}
    />
  );
});

export function Label({ children, htmlFor, className }: { children: ReactNode; htmlFor?: string; className?: string }) {
  return (
    <label htmlFor={htmlFor} className={cn("micro mb-1.5 block text-muted", className)}>
      {children}
    </label>
  );
}

// ------------------------------------------------------------------ Pills, badges, dots

export function Pill({ children, tone = "neutral", className }: { children: ReactNode; tone?: "neutral" | "danger" | "warning" | "success" | "info" | "accent"; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-full border px-2 text-meta font-medium",
        tone === "neutral" && "border-border bg-surface-2 text-muted",
        tone === "danger" && "border-transparent bg-[color-mix(in_oklab,var(--danger)_12%,transparent)] text-danger-text",
        tone === "warning" && "border-transparent bg-[color-mix(in_oklab,var(--warning)_14%,transparent)] text-warning-text",
        tone === "success" && "border-transparent bg-[color-mix(in_oklab,var(--success)_14%,transparent)] text-success-text",
        tone === "info" && "border-transparent bg-[color-mix(in_oklab,var(--info)_12%,transparent)] text-info-text",
        tone === "accent" && "border-transparent bg-[color-mix(in_oklab,var(--accent)_16%,transparent)] text-accent-text",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function CourseDot({ index, className }: { index: number | null | undefined; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block h-2 w-2 shrink-0 rounded-full", className)}
      style={{ background: index == null ? "var(--accent)" : `var(--course-${index % 8})` }}
    />
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-border bg-surface-2 px-1.5 py-0.5 font-ui text-meta text-muted">{children}</kbd>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-card bg-surface-2", className)} aria-hidden />;
}

// ------------------------------------------------------------------ Tooltip

export function Tip({ children, content, side = "top" }: { children: ReactNode; content: ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <TooltipP.Root delayDuration={300}>
      <TooltipP.Trigger asChild>{children}</TooltipP.Trigger>
      <TooltipP.Portal>
        <TooltipP.Content
          side={side}
          sideOffset={6}
          className="z-50 max-w-xs rounded-lg border border-border bg-surface px-3 py-2 text-small text-text shadow-lift"
        >
          {content}
        </TooltipP.Content>
      </TooltipP.Portal>
    </TooltipP.Root>
  );
}

// ------------------------------------------------------------------ Status toggle (circle → check)

export function StatusToggle({ status, onToggle, label }: { status: MyStatus; onToggle: () => void; label: string }) {
  const done = status === "submitted";
  const Icon = done ? Check : status === "in_progress" ? CircleDot : status === "not_applicable" ? Minus : Circle;
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      onPointerDown={(e) => e.stopPropagation()}
      aria-pressed={done}
      aria-label={done ? `Mark "${label}" as pending` : `Mark "${label}" as submitted`}
      className={cn(
        "grid h-7 w-7 shrink-0 place-items-center rounded-full border transition-colors duration-toggle ease-ez",
        done ? "border-success bg-success text-primary-fg" : "border-border text-faint hover:border-success hover:text-success-text",
      )}
    >
      <Icon size={done ? 14 : 16} strokeWidth={done ? 2.5 : 1.5} />
    </button>
  );
}

// ------------------------------------------------------------------ Segmented control

export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-lg bg-surface-2 p-1">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "h-8 rounded-md px-3 text-small transition-colors duration-toggle",
            value === o.value ? "bg-surface text-text shadow-card" : "text-muted hover:text-text",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <p className="font-display text-h3 text-text">{title}</p>
      {body && <p className="max-w-sm text-small text-muted">{body}</p>}
      {action}
    </div>
  );
}
