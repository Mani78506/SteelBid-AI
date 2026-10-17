import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, AlertCircle, Info } from "lucide-react";

type Toast = { id: number; kind: "success" | "error" | "info"; message: string };
const ToastCtx = React.createContext<{ push: (kind: Toast["kind"], message: string) => void }>({ push: () => {} });

export function useToast() {
  return React.useContext(ToastCtx);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);
  const counter = React.useRef(0);
  const push = React.useCallback((kind: Toast["kind"], message: string) => {
    const id = ++counter.current;
    setToasts((t) => [...t, { id, kind, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2" aria-live="polite">
        <AnimatePresence>
          {toasts.map((t) => (
            <motion.div key={t.id}
              initial={{ opacity: 0, y: 10, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: 24 }} transition={{ duration: 0.18 }}
              className="flex items-start gap-2 rounded-lg border border-border bg-card px-3 py-2.5 shadow-lg">
              {t.kind === "success" && <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />}
              {t.kind === "error" && <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />}
              {t.kind === "info" && <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary-600" />}
              <p className="text-xs leading-snug text-foreground">{t.message}</p>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  );
}
