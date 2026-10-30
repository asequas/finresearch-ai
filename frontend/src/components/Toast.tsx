import { type ReactNode, createContext, useCallback, useContext, useState } from "react";

type Toast = { id: number; text: string; tone: "info" | "error" };
const ToastContext = createContext<(text: string, tone?: Toast["tone"]) => void>(() => {});

/** Brief confirmation of an action ("Research queued", "Job cancelled"). Announced to screen readers. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = Date.now() + Math.random();
    setToasts((all) => [...all.slice(-2), { id, text, tone }]);
    setTimeout(() => setToasts((all) => all.filter((t) => t.id !== id)), 4200);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" role="status" className="no-print pointer-events-none fixed right-4 bottom-20 z-50 flex flex-col items-end gap-2 md:bottom-6">
        {toasts.map((t) => (
          <div key={t.id} className="toast-in pointer-events-auto rounded-[6px] bg-raised px-4 py-2.5 text-ink shadow-[var(--shadow)]">
            {t.tone === "error" && <span className="mr-2 inline-block h-1.5 w-1.5 rounded-full bg-negative align-middle" aria-hidden="true" />}
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
