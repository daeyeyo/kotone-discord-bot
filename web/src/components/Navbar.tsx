import Link from "next/link";
import {
  BookOpen,
  LayoutGrid,
  LogIn,
  LogOut,
  ShieldCheck,
  Sparkles,
  Trophy,
} from "lucide-react";
import { auth, isDiscordAuthConfigured, signInWithDiscord, signOutUser } from "@/auth";

export async function Navbar() {
  const session = await auth();
  const user = session?.user;

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-[#07070d]/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-6">
          <Link
            href="/"
            className="group flex items-center gap-2.5 text-white transition-opacity hover:opacity-90"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#ff6b8b] via-[#c084fc] to-[#22d3ee] text-sm font-black text-white shadow-[0_0_20px_-4px_rgba(255,107,139,0.75)]">
              K
            </span>
            <div className="leading-tight">
              <div className="flex items-center gap-2">
                <span className="text-base font-bold tracking-tight">
                  Kotone<span className="text-[#ff6b8b]">.binder</span>
                </span>
                <span className="hidden items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300 sm:inline-flex">
                  <ShieldCheck className="h-3 w-3" />
                  Read-Only
                </span>
              </div>
              <p className="hidden text-[11px] text-zinc-400 sm:block">
                tripleS Photocard Companion
              </p>
            </div>
          </Link>

          <nav className="hidden items-center gap-1 md:flex">
            <Link
              href="/collection"
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-zinc-300 transition hover:bg-white/5 hover:text-white"
            >
              <LayoutGrid className="h-4 w-4 text-[#ff6b8b]" />
              My Binder
            </Link>
            <Link
              href="/leaderboard"
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-zinc-300 transition hover:bg-white/5 hover:text-white"
            >
              <Trophy className="h-4 w-4 text-amber-300" />
              Leaderboards
            </Link>
            <Link
              href="/codex"
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-zinc-300 transition hover:bg-white/5 hover:text-white"
            >
              <BookOpen className="h-4 w-4 text-sky-300" />
              Card Codex
            </Link>
          </nav>
        </div>

        <div className="flex items-center gap-2.5">
          {user?.id ? (
            <div className="flex items-center gap-2">
              <Link
                href="/collection"
                className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 py-1 pl-1.5 pr-3 text-sm font-medium text-zinc-100 transition hover:border-[#ff6b8b]/50 hover:bg-white/10"
              >
                {user.image ? (
                  <img
                    src={user.image}
                    alt={user.name ?? "Discord Avatar"}
                    className="h-6 w-6 rounded-full object-cover ring-1 ring-white/20"
                  />
                ) : (
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#ff6b8b]/20 text-xs font-bold text-[#ff6b8b]">
                    {(user.name ?? "U")[0].toUpperCase()}
                  </span>
                )}
                <span className="max-w-[120px] truncate">
                  {user.name ?? user.username ?? "Collector"}
                </span>
              </Link>
              <form
                action={async () => {
                  "use server";
                  await signOutUser("/");
                }}
              >
                <button
                  type="submit"
                  title="Sign out"
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 text-xs font-medium text-zinc-300 transition hover:border-white/20 hover:bg-white/10 hover:text-white"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">Sign Out</span>
                </button>
              </form>
            </div>
          ) : isDiscordAuthConfigured ? (
            <form
              action={async () => {
                "use server";
                await signInWithDiscord("/collection");
              }}
            >
              <button
                type="submit"
                className="inline-flex h-9 items-center gap-2 rounded-xl bg-[#5865F2] px-3.5 text-sm font-semibold text-white shadow-[0_0_20px_-4px_rgba(88,101,242,0.75)] transition hover:bg-[#4752C4]"
              >
                <LogIn className="h-4 w-4" />
                <span>Login with Discord</span>
              </button>
            </form>
          ) : (
            <Link
              href="/login"
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-[#5865F2]/50 bg-[#5865F2]/15 px-3.5 text-sm font-semibold text-indigo-200 transition hover:bg-[#5865F2]/25"
            >
              <Sparkles className="h-4 w-4 text-[#ff6b8b]" />
              <span>Setup Discord Login</span>
            </Link>
          )}
        </div>
      </div>

      {/* Mobile bottom-strip navigation */}
      <nav className="flex items-center justify-around border-t border-white/5 px-2 py-1.5 md:hidden">
        <Link
          href="/collection"
          className="flex items-center gap-1.5 rounded-lg px-3 py-1 text-xs font-medium text-zinc-300 hover:text-white"
        >
          <LayoutGrid className="h-3.5 w-3.5 text-[#ff6b8b]" />
          My Binder
        </Link>
        <Link
          href="/leaderboard"
          className="flex items-center gap-1.5 rounded-lg px-3 py-1 text-xs font-medium text-zinc-300 hover:text-white"
        >
          <Trophy className="h-3.5 w-3.5 text-amber-300" />
          Leaderboards
        </Link>
        <Link
          href="/codex"
          className="flex items-center gap-1.5 rounded-lg px-3 py-1 text-xs font-medium text-zinc-300 hover:text-white"
        >
          <BookOpen className="h-3.5 w-3.5 text-sky-300" />
          Codex
        </Link>
      </nav>
    </header>
  );
}
