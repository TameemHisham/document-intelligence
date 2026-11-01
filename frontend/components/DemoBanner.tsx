"use client";

import { useRouter } from "next/navigation";
import { FlaskConical, PencilRuler, RotateCcw } from "lucide-react";
import { api, restoreOwnerToken, setToken, type Usage, type User } from "@/lib/api";

function hoursLeft(iso: string) {
  const h = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 3_600_000));
  return h >= 1 ? `${h}h` : "under an hour";
}

/** Shown to demo guests (sandbox info + limits) and to the owner while editing the demo library. */
export function DemoBanner({ user, usage }: { user: User; usage: Usage | null }) {
  const router = useRouter();

  if (user.is_template)
    return (
      <div className="flex flex-wrap items-center gap-2 bg-accent px-4 py-2 text-xs text-white md:px-8">
        <PencilRuler className="h-3.5 w-3.5" />
        <span className="flex-1">Editing the demo library. Every new guest starts with a copy of what&apos;s here.</span>
        <button
          onClick={() => {
            restoreOwnerToken();
            location.assign("/");
          }}
          className="rounded bg-white/20 px-2 py-1 font-medium hover:bg-white/30"
        >
          Back to my library
        </button>
      </div>
    );

  if (!user.is_guest) return null;
  const restart = async () => {
    if (!confirm("Start a fresh sandbox? Your changes here will be discarded.")) return;
    const res = await api<{ token: string }>("/auth/guest", { method: "POST" });
    setToken(res.token);
    router.replace("/");
    location.reload();
  };

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 bg-ink px-4 py-2 text-xs text-white md:px-8">
      <FlaskConical className="h-3.5 w-3.5" />
      <span className="font-medium">Demo sandbox</span>
      <span className="opacity-80">Explore freely. Your changes are private and reset in {user.expires_at ? hoursLeft(user.expires_at) : "24h"}.</span>
      {usage?.demo && (
        <span className="opacity-80">
          · {usage.demo.questions_left} questions · {usage.demo.uploads_left} uploads left
        </span>
      )}
      <button onClick={restart} className="ml-auto flex items-center gap-1 rounded bg-white/15 px-2 py-1 hover:bg-white/25">
        <RotateCcw className="h-3 w-3" /> Start over
      </button>
    </div>
  );
}
