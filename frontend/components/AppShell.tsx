"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { Camera, FolderKanban, FolderOpen, Images, Inbox, Layers, LogOut, PencilRuler, Search, Star, UploadCloud } from "lucide-react";
import { api, clearToken, getToken, stashOwnerToken, setToken, type Category, type Usage, type User } from "@/lib/api";
import { DemoBanner } from "./DemoBanner";
import { useApi } from "@/lib/hooks";

const mobileNav = [
  { href: "/", label: "Library", icon: Images },
  { href: "/search", label: "Search", icon: Search },
  { href: "/categories", label: "Categories", icon: Layers },
  { href: "/projects", label: "Projects", icon: FolderKanban },
];

const noopSubscribe = () => () => {};

const initials = (u: User | null) => (u?.name || u?.email || "?").slice(0, 2).toUpperCase();

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [q, setQ] = useState("");
  const authed = !!useSyncExternalStore(noopSubscribe, getToken, () => null);
  const { data: user } = useApi<User>(authed ? "/auth/me" : null);
  const { data: categories } = useApi<Category[]>(authed ? `/categories?r=${pathname}` : null);
  const { data: spend } = useApi<Usage>(authed ? `/usage?r=${pathname}` : null);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        document.getElementById("global-search")?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!authed) return null;

  const logout = () => {
    clearToken();
    router.replace("/login");
  };
  const editDemoLibrary = async () => {
    const res = await api<{ token: string }>("/auth/demo-template", { method: "POST" });
    stashOwnerToken();
    setToken(res.token);
    location.assign("/");
  };
  const libraryName = user?.is_template ? "Demo library" : user?.is_guest ? "Demo sandbox" : user?.name ? `${user.name}'s Library` : "Library";
  const active = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col overflow-y-auto border-r border-line bg-[#eaf2ec] p-5 md:flex">
        <div className="mb-6 flex items-center gap-3">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-ink text-xs font-medium text-white">{initials(user)}</span>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium leading-tight">{libraryName}</p>
            <p className="eyebrow">Personal Vault</p>
          </div>
        </div>
        <p className="eyebrow mb-2">Library</p>
        <nav className="space-y-1 text-sm">
          <SideLink href="/" icon={<Images className="h-4 w-4" />} on={pathname === "/"}>All Photos</SideLink>
          <SideLink href="/?tab=favorites" icon={<Star className="h-4 w-4" />} on={false}>Favorites</SideLink>
          <SideLink href="/?tab=unfiled" icon={<Inbox className="h-4 w-4" />} on={false}>Needs category</SideLink>
          <SideLink href="/search" icon={<Search className="h-4 w-4" />} on={active("/search")}>Search</SideLink>
          <SideLink href="/categories" icon={<Layers className="h-4 w-4" />} on={active("/categories")}>Categories</SideLink>
          <SideLink href="/projects" icon={<FolderKanban className="h-4 w-4" />} on={active("/projects")}>Projects</SideLink>
          <SideLink href="/upload" icon={<UploadCloud className="h-4 w-4" />} on={active("/upload")}>Upload</SideLink>
        </nav>
        <p className="eyebrow mb-2 mt-7">Your categories</p>
        <nav className="space-y-1 text-sm">
          {categories?.map((c) => (
            <Link
              key={c.id}
              href={`/categories/${c.id}`}
              className="flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-muted hover:bg-white/60"
            >
              <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: c.color }} />
              <span className="truncate">{c.name}</span>
              <span className="ml-auto font-mono text-[10px]">{c.count || ""}</span>
            </Link>
          ))}
        </nav>
        {user?.is_owner && user.demo_enabled && (
          <button onClick={editDemoLibrary} className="mt-6 flex items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm text-muted hover:bg-white/60">
            <PencilRuler className="h-4 w-4" /> Edit demo library
          </button>
        )}
        {spend && !user?.is_guest && (
          <div className="mt-auto pt-6" title="AI + OCR spend this month (hard cap)">
            <p className="eyebrow mb-1">
              AI budget ${spend.month_spent_usd.toFixed(2)} / ${spend.monthly_budget_usd.toFixed(2)}
            </p>
            <div className="h-1 overflow-hidden rounded bg-line">
              <div
                className="h-full bg-ink"
                style={{ width: `${Math.min(100, (100 * spend.month_spent_usd) / Math.max(spend.monthly_budget_usd, 0.01))}%` }}
              />
            </div>
          </div>
        )}
        <button onClick={logout} className={`eyebrow flex items-center justify-center gap-1.5 pt-4 hover:text-ink ${user?.is_guest ? "mt-auto" : ""}`}>
          <LogOut className="h-3 w-3" /> {user?.is_guest ? "Leave demo" : "Sign out"}
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col pb-20 md:pb-0">
        {user && <DemoBanner user={user} usage={spend} />}
        <header className="flex items-center justify-between px-4 py-3 md:hidden">
          <Link href="/" className="flex items-center gap-2 font-serif text-xl">
            <FolderOpen className="h-5 w-5" /> Library
          </Link>
          <button onClick={logout} aria-label="Sign out" className="grid h-8 w-8 place-items-center rounded-full bg-ink text-xs text-white">
            {initials(user)}
          </button>
        </header>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (q.trim()) router.push(`/search?q=${encodeURIComponent(q)}`);
          }}
          className="hidden px-8 pt-6 md:block"
        >
          <div className="flex items-center gap-3 rounded-lg border border-line bg-card px-4 py-2.5">
            <Search className="h-4 w-4 text-muted" />
            <input
              id="global-search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search your photos, notes, or receipts…"
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted"
            />
            <kbd className="rounded border border-line px-1.5 font-mono text-[10px] text-muted">⌘K</kbd>
            <button type="submit" aria-label="Search" className="grid h-7 w-7 place-items-center rounded bg-ink text-white">→</button>
          </div>
        </form>

        <main className="flex-1 px-4 py-5 pb-28 md:px-8 md:pb-10">{children}</main>
      </div>

      <Link
        href="/upload"
        aria-label="Upload"
        className={`fixed bottom-20 right-4 z-20 grid h-12 w-12 place-items-center rounded-xl bg-ink text-white shadow-lg md:hidden ${active("/upload") ? "hidden" : ""}`}
      >
        <Camera className="h-5 w-5" />
      </Link>
      <nav className="fixed inset-x-0 bottom-0 z-20 flex justify-around border-t border-line bg-card pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] md:hidden">
        {mobileNav.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} className={`flex flex-col items-center gap-0.5 px-3 text-[10px] ${active(href) ? "text-ink" : "text-muted"}`}>
            <Icon className="h-5 w-5" />
            {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}

function SideLink({ href, icon, on, children }: { href: string; icon: React.ReactNode; on: boolean; children: React.ReactNode }) {
  return (
    <Link href={href} className={`flex items-center gap-2.5 rounded-md px-2.5 py-1.5 ${on ? "bg-ink text-white" : "text-muted hover:bg-white/60"}`}>
      {icon}
      {children}
    </Link>
  );
}
