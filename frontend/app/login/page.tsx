"use client";

import Script from "next/script";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { FlaskConical, FolderOpen } from "lucide-react";
import { api, getToken, json, setToken, type User } from "@/lib/api";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";
const DEV_AUTH = process.env.NEXT_PUBLIC_DEV_AUTH === "true";
const DEMO = process.env.NEXT_PUBLIC_DEMO === "true";

type GoogleId = {
  initialize: (o: { client_id: string; callback: (r: { credential: string }) => void }) => void;
  renderButton: (el: HTMLElement, o: Record<string, unknown>) => void;
};
declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
  }
}

export default function LoginPage() {
  const router = useRouter();
  const buttonRef = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState("");
  const [gisLoaded, setGisLoaded] = useState(false);

  useEffect(() => {
    if (getToken()) router.replace("/");
  }, [router]);

  const finish = useCallback(
    async (path: string, body: object) => {
      try {
        const res = await api<{ token: string; user: User }>(path, path === "/auth/guest" ? { method: "POST" } : json("POST", body));
        setToken(res.token);
        router.replace("/");
      } catch (e) {
        setErr((e as Error).message);
      }
    },
    [router],
  );

  useEffect(() => {
    if (!gisLoaded || !GOOGLE_CLIENT_ID || !window.google || !buttonRef.current) return;
    window.google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      callback: (r) => finish("/auth/google", { credential: r.credential }),
    });
    window.google.accounts.id.renderButton(buttonRef.current, { theme: "outline", size: "large", width: 300, text: "continue_with" });
  }, [gisLoaded, finish]);

  return (
    <main className="grid min-h-screen place-items-center px-4">
      <Script src="https://accounts.google.com/gsi/client" strategy="afterInteractive" onLoad={() => setGisLoaded(true)} />
      <div className="w-full max-w-sm rounded-2xl border border-line bg-card p-8 text-center shadow-sm">
        <span className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-xl bg-ink text-white">
          <FolderOpen className="h-6 w-6" />
        </span>
        <p className="eyebrow mb-1">Thoughtful Personal Archive</p>
        <h1 className="font-serif text-3xl">Document Intelligence</h1>
        <p className="mb-6 mt-2 text-sm text-muted">A quiet library for your photos and documents, ready to answer questions.</p>

        {DEMO && (
          <>
            <button
              onClick={() => finish("/auth/guest", {})}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-ink py-3 text-sm font-medium text-white hover:opacity-90"
            >
              <FlaskConical className="h-4 w-4" /> Try the demo, no sign-up
            </button>
            <p className="mb-5 mt-2 text-xs text-muted">
              You get a private sandbox with sample photos and documents. Search, sort, upload and ask questions. It resets after 24 hours.
            </p>
            <p className="eyebrow mb-3">Owner sign-in</p>
          </>
        )}
        {GOOGLE_CLIENT_ID ? (
          <div ref={buttonRef} className="flex justify-center" />
        ) : (
          <p className="text-xs text-muted">Set NEXT_PUBLIC_GOOGLE_CLIENT_ID to enable Google sign-in.</p>
        )}

        {DEV_AUTH && (
          <button
            onClick={() => finish("/auth/dev", { email: "dev@example.com" })}
            className="mt-4 w-full rounded-lg border border-dashed border-line py-2 text-xs text-muted hover:text-ink"
          >
            Dev login (local only)
          </button>
        )}
        {err && <p className="mt-3 text-xs text-accent">{err}</p>}
      </div>
    </main>
  );
}
