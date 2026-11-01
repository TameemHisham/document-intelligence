"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { Check, TriangleAlert, X } from "lucide-react";

type Toast = { id: number; text: string; kind: "ok" | "error"; action?: { label: string; run: () => void } };
type Ctx = (text: string, opts?: { kind?: "ok" | "error"; action?: Toast["action"] }) => void;

const ToastContext = createContext<Ctx>(() => {});
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = (id: number) => setToasts((t) => t.filter((x) => x.id !== id));

  const show = useCallback<Ctx>((text, opts = {}) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-2), { id, text, kind: opts.kind ?? "ok", action: opts.action }]);
    setTimeout(() => dismiss(id), opts.kind === "error" ? 6000 : 3500);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex flex-col items-center gap-2 px-4 md:bottom-6" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto flex max-w-md items-center gap-3 rounded-lg bg-ink px-4 py-2.5 text-sm text-white shadow-lg"
          >
            {t.kind === "error" ? <TriangleAlert className="h-4 w-4 shrink-0 text-[#f6b7a6]" /> : <Check className="h-4 w-4 shrink-0" />}
            <span>{t.text}</span>
            {t.action && (
              <button onClick={() => { t.action!.run(); dismiss(t.id); }} className="font-medium underline underline-offset-2">
                {t.action.label}
              </button>
            )}
            <button onClick={() => dismiss(t.id)} aria-label="Dismiss" className="opacity-60 hover:opacity-100">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
