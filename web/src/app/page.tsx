import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Coins,
  Layers,
  ShieldCheck,
  Sparkles,
  Tag,
  Trophy,
  Users,
} from "lucide-react";
import { auth, isDiscordAuthConfigured, signInWithDiscord } from "@/auth";
import { ERA_ORDER, S_ORDER } from "@/lib/catalog";
import {
  enrichLeaderboardWithDiscord,
  getLeaderboard,
} from "@/lib/db/leaderboards";
import { getCommunitySummary, getPlayerProfile } from "@/lib/db/players";
import {
  formatFallbackDisplayName,
  getStoredDisplayName,
  resolveDiscordUser,
} from "@/lib/discord-users";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const session = await auth();
  const viewerId = session?.user?.id || null;
  const viewerProfile = viewerId ? getPlayerProfile(viewerId) : null;
  let viewerDisplayName = viewerProfile
    ? getStoredDisplayName(viewerProfile.displayName, viewerProfile.username)
    : null;
  if (!viewerDisplayName) {
    viewerDisplayName = session?.user?.name ?? null;
  }
  if (!viewerDisplayName && viewerProfile) {
    const discordViewer = await resolveDiscordUser(viewerProfile.userId);
    viewerDisplayName =
      discordViewer?.displayName ??
      formatFallbackDisplayName(viewerProfile.userId);
  }

  let summary = {
    totalPlayers: 0,
    totalCards: 0,
    totalMarketListings: 0,
    totalComo: 0,
  };
  let topCollectors: ReturnType<typeof getLeaderboard>["entries"] = [];
  let dbError: string | null = null;

  try {
    summary = getCommunitySummary();
    const globalBoard = getLeaderboard({ kind: "global", viewerId });
    const enrichedBoard = await enrichLeaderboardWithDiscord(
      globalBoard,
      viewerId,
      { limit: 5 }
    );
    topCollectors = enrichedBoard.entries.slice(0, 5);
  } catch (err) {
    dbError =
      err instanceof Error
        ? err.message
        : "Could not read shared SQLite database.";
  }

  return (
    <div className="space-y-10">
      {/* Hero Banner */}
      <section className="relative overflow-hidden rounded-3xl border border-white/10 bg-[#10101a]/90 p-7 shadow-2xl sm:p-10">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-[#ff6b8b]/15 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 left-1/4 h-72 w-72 rounded-full bg-violet-500/15 blur-3xl" />

        <div className="relative flex flex-col justify-between gap-8 lg:flex-row lg:items-center">
          <div className="max-w-2xl space-y-4">
            <span className="inline-flex items-center gap-2 rounded-full border border-[#ff6b8b]/35 bg-[#ff6b8b]/10 px-3 py-1 text-xs font-semibold text-[#ff9bb0]">
              <Sparkles className="h-3.5 w-3.5" />
              Kotone Bot Web Companion • Phase 1
            </span>
            <h1 className="text-3xl font-black tracking-tight text-white sm:text-5xl">
              Your tripleS Photocard Binder,{" "}
              <span className="bg-gradient-to-r from-[#ff6b8b] via-fuchsia-300 to-cyan-300 bg-clip-text text-transparent">
                Live on the Web.
              </span>
            </h1>
            <p className="text-sm leading-relaxed text-zinc-300 sm:text-base">
              Browse every card in your Discord inventory, inspect training
              skills and animated Legendary previews, track Era completion across
              all {S_ORDER.length} members and {ERA_ORDER.length} eras, and
              climb the global leaderboards—synced read-only with{" "}
              <code className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-xs text-pink-200">
                kpop_cards.db
              </code>
              .
            </p>

            <div className="flex flex-wrap items-center gap-3 pt-2">
              {viewerId ? (
                <Link
                  href="/collection"
                  className="inline-flex items-center gap-2 rounded-xl bg-[#ff6b8b] px-5 py-2.5 text-sm font-bold text-white shadow-[0_0_24px_-4px_rgba(255,107,139,0.8)] transition hover:bg-[#ff547a]"
                >
                  Open My Binder
                  <ArrowRight className="h-4 w-4" />
                </Link>
              ) : isDiscordAuthConfigured ? (
                <form
                  action={async () => {
                    "use server";
                    await signInWithDiscord("/collection");
                  }}
                >
                  <button
                    type="submit"
                    className="inline-flex items-center gap-2 rounded-xl bg-[#5865F2] px-5 py-2.5 text-sm font-bold text-white shadow-[0_0_24px_-4px_rgba(88,101,242,0.8)] transition hover:bg-[#4752C4]"
                  >
                    Login with Discord
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </form>
              ) : (
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 rounded-xl bg-[#5865F2] px-5 py-2.5 text-sm font-bold text-white shadow-[0_0_24px_-4px_rgba(88,101,242,0.8)] transition hover:bg-[#4752C4]"
                >
                  Configure Discord Login
                  <ArrowRight className="h-4 w-4" />
                </Link>
              )}

              <Link
                href="/leaderboard"
                className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/5 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10"
              >
                <Trophy className="h-4 w-4 text-amber-300" />
                Leaderboards
              </Link>

              <Link
                href="/codex"
                className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/5 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10"
              >
                <BookOpen className="h-4 w-4 text-sky-300" />
                Card Codex
              </Link>
            </div>
          </div>

          {/* Live Player Snapshot or Phase 1 Safety Card */}
          {viewerProfile ? (
            <div className="w-full max-w-sm rounded-2xl border border-[#ff6b8b]/30 bg-black/40 p-5">
              <p className="text-xs font-semibold uppercase tracking-wider text-[#ff9bb0]">
                Signed In Snapshot
              </p>
              <p className="mt-1 text-xl font-extrabold text-white">
                {viewerDisplayName ?? "Collector"}
              </p>
              <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-xl bg-white/5 p-3">
                  <p className="text-xs text-zinc-400">Cards Owned</p>
                  <p className="text-lg font-bold text-white">
                    {viewerProfile.totalCards.toLocaleString()}
                  </p>
                </div>
                <div className="rounded-xl bg-white/5 p-3">
                  <p className="text-xs text-zinc-400">COMO Balance</p>
                  <p className="text-lg font-bold text-amber-300">
                    {viewerProfile.como.toLocaleString()}
                  </p>
                </div>
              </div>
              <Link
                href="/collection"
                className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-xl bg-white/10 py-2 text-xs font-semibold text-white transition hover:bg-white/15"
              >
                View Full Collection & Era Tracker
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          ) : (
            <div className="w-full max-w-sm rounded-2xl border border-emerald-500/25 bg-black/40 p-5">
              <div className="flex items-center gap-2 text-emerald-300">
                <ShieldCheck className="h-5 w-5" />
                <span className="text-sm font-bold">
                  Zero-Lock Read-Only Mode
                </span>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-zinc-300">
                Phase 1 opens your shared SQLite database strictly in read-only
                mode so your live Discord bot never experiences write lock
                conflicts. Click any collector on the leaderboard below to
                preview their binder right away.
              </p>
            </div>
          )}
        </div>
      </section>

      {dbError && (
        <div className="rounded-2xl border border-rose-500/40 bg-rose-950/30 p-4 text-sm text-rose-200">
          <strong>Database Connection Notice:</strong> {dbError}
        </div>
      )}

      {/* Live Community Stats */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-2xl border border-white/10 bg-[#10101a]/80 p-5">
          <div className="flex items-center gap-2 text-xs font-medium text-zinc-400">
            <Users className="h-4 w-4 text-sky-300" />
            Registered Collectors
          </div>
          <p className="mt-2 text-3xl font-black text-white">
            {summary.totalPlayers.toLocaleString()}
          </p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-[#10101a]/80 p-5">
          <div className="flex items-center gap-2 text-xs font-medium text-zinc-400">
            <Layers className="h-4 w-4 text-[#ff6b8b]" />
            Cards in Circulation
          </div>
          <p className="mt-2 text-3xl font-black text-white">
            {summary.totalCards.toLocaleString()}
          </p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-[#10101a]/80 p-5">
          <div className="flex items-center gap-2 text-xs font-medium text-zinc-400">
            <Coins className="h-4 w-4 text-amber-300" />
            Total Economy COMO
          </div>
          <p className="mt-2 text-3xl font-black text-white">
            {summary.totalComo.toLocaleString()}
          </p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-[#10101a]/80 p-5">
          <div className="flex items-center gap-2 text-xs font-medium text-zinc-400">
            <Tag className="h-4 w-4 text-emerald-300" />
            Active Market Listings
          </div>
          <p className="mt-2 text-3xl font-black text-white">
            {summary.totalMarketListings.toLocaleString()}
          </p>
        </div>
      </section>

      {/* Top Collectors Preview */}
      <section className="rounded-3xl border border-white/10 bg-[#10101a]/90 p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-extrabold text-white">
              Top Global Collectors
            </h2>
            <p className="text-xs text-zinc-400">
              Click any collector to inspect their photocard binder & era
              completion progress.
            </p>
          </div>
          <Link
            href="/leaderboard"
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#ff9bb0] hover:text-white"
          >
            View all leaderboards
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>

        {topCollectors.length === 0 ? (
          <p className="mt-6 text-sm text-zinc-400">
            No cards have been collected yet.
          </p>
        ) : (
          <div className="mt-4 divide-y divide-white/5 overflow-hidden rounded-2xl border border-white/10 bg-black/30">
            {topCollectors.map((entry) => (
              <Link
                key={entry.userId}
                href={`/profile/${entry.userId}`}
                className="flex items-center justify-between gap-4 px-4 py-3 transition hover:bg-white/[0.04]"
              >
                <div className="flex items-center gap-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/5 font-mono text-xs font-bold text-amber-300">
                    #{entry.rank}
                  </span>
                  {entry.avatarUrl ? (
                    <img
                      src={entry.avatarUrl}
                      alt={entry.name}
                      className="h-8 w-8 shrink-0 rounded-full object-cover ring-1 ring-white/15"
                    />
                  ) : (
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#ff6b8b]/30 to-violet-500/30 text-xs font-bold text-white ring-1 ring-white/15">
                      {entry.name[0]?.toUpperCase() ?? "K"}
                    </span>
                  )}
                  <span className="font-bold text-white">{entry.name}</span>
                </div>
                <div className="text-right">
                  <p className="text-sm font-bold text-white">
                    {entry.primary}
                  </p>
                  <p className="text-xs text-zinc-400">{entry.secondary}</p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
