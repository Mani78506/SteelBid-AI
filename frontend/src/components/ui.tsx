import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

/* ---------- Button ---------- */
type BtnVariant = "default" | "secondary" | "outline" | "ghost" | "destructive" | "accent";
export const Button = React.forwardRef<HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: "sm" | "md" | "lg"; loading?: boolean }
>(function Button({ className, variant = "default", size = "md", loading, children, disabled, ...props }, ref) {
  const variants: Record<BtnVariant, string> = {
    default: "bg-primary text-primary-foreground hover:bg-primary-700 shadow-sm",
    accent: "bg-accent text-accent-foreground hover:opacity-90 shadow-sm",
    secondary: "bg-secondary text-secondary-foreground hover:bg-slate-200",
    outline: "border border-input bg-card hover:bg-muted",
    ghost: "hover:bg-muted text-foreground",
    destructive: "bg-destructive text-destructive-foreground hover:opacity-90",
  };
  const sizes = { sm: "h-8 px-3 text-xs", md: "h-9 px-4 text-sm", lg: "h-10 px-5 text-sm" };
  return (
    <button ref={ref} disabled={disabled || loading}
      className={cn("inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 disabled:pointer-events-none",
        variants[variant], sizes[size], className)} {...props}>
      {loading && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </button>
  );
});

/* ---------- Card ---------- */
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("min-w-0 rounded-lg border border-border bg-card text-card-foreground shadow-card", className)} {...props} />;
}
export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex items-start justify-between gap-2 px-4 pt-4 pb-2", className)} {...props} />;
}
export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-sm font-semibold tracking-tight text-foreground", className)} {...props} />;
}
export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-4 pb-4", className)} {...props} />;
}

/* ---------- Input / Select / Label ---------- */
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return <input ref={ref} className={cn(
      "flex h-9 w-full rounded-md border border-input bg-card px-3 text-sm shadow-sm transition-colors",
      "placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      "disabled:cursor-not-allowed disabled:opacity-50", className)} {...props} />;
  });
export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, ...props }, ref) {
    return <select ref={ref} className={cn(
      "flex h-9 w-full rounded-md border border-input bg-card px-2.5 text-sm shadow-sm",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50", className)} {...props} />;
  });
export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("mb-1.5 block text-xs font-medium text-foreground/80", className)} {...props} />;
}

/* ---------- Badge ---------- */
const badgeTones: Record<string, string> = {
  default: "bg-slate-100 text-slate-700 border-slate-200",
  blue: "bg-primary-50 text-primary-700 border-primary-100",
  green: "bg-emerald-50 text-emerald-700 border-emerald-200",
  amber: "bg-amber-50 text-amber-700 border-amber-200",
  red: "bg-red-50 text-red-700 border-red-200",
  teal: "bg-teal-50 text-teal-700 border-teal-200",
};
const statusTone: Record<string, string> = {
  ACTIVE: "blue", OK: "green", APPROVED: "green", ACCEPTED: "green", FULFILLED: "green",
  RECEIVED: "green", IN_STOCK: "green", COMPLETED: "green", PAID: "green", VERIFIED: "green",
  OPEN: "blue", DRAFT: "default", PENDING_APPROVAL: "amber", PENDING_REVIEW: "amber",
  QUARANTINED: "amber", PARTIAL: "amber", SUBMITTED: "blue", IN_PROGRESS: "blue",
  SHORTAGE: "red", REJECTED: "red", EXPIRED: "red", CANCELLED: "red", OVERDUE: "red",
  BLOCKED: "red", FAILED: "red", UNCONFIRMED: "amber", CONFIRMED: "green", ISSUED: "blue",
  CONVERTED: "teal", ORDERED: "blue", SHIPPED: "teal", DELIVERED: "green", PLANNED: "default",
};
export function Badge({ value, className }: { value: string; className?: string }) {
  const tone = statusTone[value] ?? "default";
  return <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap",
    badgeTones[tone], className)}>{value.replace(/_/g, " ")}</span>;
}

/* ---------- Skeleton ---------- */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} />;
}

/* ---------- Modal / Drawer ---------- */
export function Modal({ open, onClose, title, children, wide }: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode; wide?: boolean;
}) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-center justify-center p-4"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-slate-900/45" onClick={onClose} />
          <motion.div role="dialog" aria-modal="true"
            className={cn("relative w-full rounded-lg bg-card shadow-xl", wide ? "max-w-4xl" : "max-w-lg")}
            initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }} transition={{ duration: 0.16 }}>
            <div className="flex items-center justify-between border-b border-border px-5 py-3">
              <h2 className="text-sm font-semibold">{title}</h2>
              <button onClick={onClose} className="rounded p-1 hover:bg-muted" aria-label="Close"><X className="h-4 w-4" /></button>
            </div>
            <div className="max-h-[78vh] overflow-y-auto p-5">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ---------- Confirm dialog ---------- */
export function Confirm({ open, onClose, onConfirm, title, message, loading }: {
  open: boolean; onClose: () => void; onConfirm: () => void;
  title: string; message: string; loading?: boolean;
}) {
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <p className="mb-5 text-sm text-muted-foreground">{message}</p>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button variant="destructive" onClick={onConfirm} loading={loading}>Confirm</Button>
      </div>
    </Modal>
  );
}

/* ---------- Empty / Error states ---------- */
export function Empty({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-border py-10 text-center">
      <p className="text-sm font-medium text-foreground">{title}</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : "Something went wrong";
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-red-200 bg-red-50 py-8 text-center">
      <p className="text-sm font-medium text-red-700">{msg}</p>
      {onRetry && <Button size="sm" variant="outline" onClick={onRetry}>Retry</Button>}
    </div>
  );
}
