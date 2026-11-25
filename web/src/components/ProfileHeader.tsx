import {
  Coins,
  Flame,
  Heart,
  Layers,
  Lock,
  Sparkles,
  Tag,
  Target,
  Timer,
} from "lucide-react";
import { RARITY_ORDER, S_MEMBERS, getRarityMeta } from "@/lib/catalog";
import type { PlayerProfile } from "@/lib/db/players";
import {
  formatFallbackDisplayName,
  getStoredDisplayName,
} from "@/lib/player-names";

interface ProfileHeaderProps {
  profile: PlayerProfile;
  displayName?: string | null;
  avatarUrl?: string | null;
  isOwnProfile?: boolean;
}

function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const parts: string[] = [];
  if (days) parts.push(`${days}d`);
  if (hours) parts.push(`${hours}h`);
  if (minutes || parts.length === 0) parts.push(`${minutes}m`);
  return parts.join(" ");
}

export function ProfileHeader({
  profile,
  displayName,
  avatarUrl,
  isOwnProfile = false,
}: ProfileHeaderProps) {
  const storedDbName = getStoredDisplayName(
    profile.displayName,
    profile.username
  );
  const resolvedName =
    displayName || storedDbName || formatFallbackDisplayName(profile.userId);
  const nowSec = Date.now() / 1000;
  const boosterRemaining = profile.activeBoosterExpiresAt
    ? Math.max(0, Math.floor(profile.activeBoosterExpiresAt - nowSec))
    : 0;

  return (
    <section className="relative overflow-hidden rounded-3xl border border-white/10 bg-[#10101a]/90 p-6 shadow-2xl sm:p-8">
      <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-[#ff6b8b]/10 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 left-1/3 h-64 w-64 rounded-full bg-violet-500/10 blur-3xl" />

      <div className="relative flex flex-col justify-between gap-6 lg:flex-row lg:items-start">
        {/* Identity & Bio */}
        <div className="flex items-start gap-4">
          {avatarUrl ? (
            <img
              src={avatarUrl}
              alt={resolvedName}
              className="h-16 w-16 rounded-2xl object-cover ring-2 ring-[#ff6b8b]/40 sm:h-20 sm:w-20"
            />
          ) : (
            <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[#ff6b8b]/30 to-violet-500/30 text-2xl font-black text-white ring-1 ring-white/15 sm:h-20 sm:w-20">
              {resolvedName[0]?.toUpperCase() ?? "K"}
            </div>
          )}

          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-extrabold tracking-tight text-white sm:text-3xl">
                {resolvedName}
              </h1>
              {isOwnProfile && (
                <span className="rounded-full border border-[#ff6b8b]/40 bg-[#ff6b8b]/15 px-2.5 py-0.5 text-xs font-semibold text-[#ff9bb0]">
                  Your Binder
                </span>
              )}
            </div>

            <p className="max-w-2xl text-sm text-zinc-300">
              {profile.bio ?? "No bio set yet. Set one in Discord with /bio set."}
            </p>

            {/* Biases & Drop Target */}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {profile.biases.length > 0 && (
                <span className="inline-flex items-center gap-1.5 rounded-xl border border-pink-400/25 bg-pink-500/10 px-2.5 py-1 text-xs font-medium text-pink-200">
                  <Heart className="h-3.5 w-3.5 text-[#ff6b8b]" />
                  Bias:{" "}
                  {profile.biases
                    .map((code) => S_MEMBERS[code]?.name ?? code)
                    .join(", ")}
                </span>
              )}

              {profile.target && (
                <span className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-400/25 bg-cyan-500/10 px-2.5 py-1 text-xs font-medium text-cyan-200">
                  <Target className="h-3.5 w-3.5 text-cyan-300" />
                  Target: {profile.target.label}
                </span>
              )}

              {boosterRemaining > 0 && (
                <span className="inline-flex items-center gap-1.5 rounded-xl border border-amber-400/35 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-200">
                  <Sparkles className="h-3.5 w-3.5 text-amber-300" />
                  Luck Booster: {formatDuration(boosterRemaining)}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Stat Tiles */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:min-w-[420px]">
          <div className="rounded-2xl border border-white/10 bg-black/30 p-3.5">
            <div className="flex items-center gap-1.5 text-xs text-zinc-400">
              <Coins className="h-3.5 w-3.5 text-amber-300" />
              COMO
            </div>
            <p className="mt-1 text-xl font-extrabold text-white">
              {profile.como.toLocaleString()}
            </p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-black/30 p-3.5">
            <div className="flex items-center gap-1.5 text-xs text-zinc-400">
              <Layers className="h-3.5 w-3.5 text-[#ff6b8b]" />
              Cards
            </div>
            <p className="mt-1 text-xl font-extrabold text-white">
              {profile.totalCards.toLocaleString()}
            </p>
            <p className="text-[11px] text-zinc-500">
              {profile.uniqueCards} unique
            </p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-black/30 p-3.5">
            <div className="flex items-center gap-1.5 text-xs text-zinc-400">
              <Flame className="h-3.5 w-3.5 text-orange-400" />
              Streak
            </div>
            <p className="mt-1 text-xl font-extrabold text-white">
              {profile.dailyStreak}d
            </p>
            <p className="text-[11px] text-zinc-500">
              {profile.effects.streakShields > 0
                ? `${profile.effects.streakShields} shield armed`
                : "Daily streak"}
            </p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-black/30 p-3.5">
            <div className="flex items-center gap-1.5 text-xs text-zinc-400">
              <Lock className="h-3.5 w-3.5 text-violet-300" />
              Protected
            </div>
            <p className="mt-1 text-xl font-extrabold text-white">
              {profile.binderCards}
            </p>
            <p className="text-[11px] text-zinc-500">
              {profile.listedCards} on market
            </p>
          </div>
        </div>
      </div>

      {/* Rarity Distribution + Active Cooldowns */}
      <div className="relative mt-6 flex flex-col gap-4 border-t border-white/10 pt-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {RARITY_ORDER.map((rarityName) => {
            const meta = getRarityMeta(rarityName);
            const count = profile.rarityCounts[rarityName] ?? 0;
            return (
              <span
                key={rarityName}
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-semibold ${meta.badgeClass}`}
              >
                <span>{rarityName}</span>
                <span className="font-mono opacity-90">{count}</span>
              </span>
            );
          })}
        </div>

        {isOwnProfile && profile.cooldowns.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-300">
            <span className="inline-flex items-center gap-1 text-zinc-400">
              <Timer className="h-3.5 w-3.5" />
              Cooldowns:
            </span>
            {profile.cooldowns.map((cd) => (
              <span
                key={cd.type}
                className="rounded-lg border border-white/10 bg-white/5 px-2 py-0.5 font-mono text-[11px]"
              >
                {cd.type}: {formatDuration(cd.remainingSeconds)}
              </span>
            ))}
          </div>
        )}

        {isOwnProfile && profile.items.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-300">
            <span className="inline-flex items-center gap-1 text-zinc-400">
              <Tag className="h-3.5 w-3.5" />
              Items:
            </span>
            {profile.items.map((item) => (
              <span
                key={item.key}
                className="rounded-lg border border-white/10 bg-white/5 px-2 py-0.5 text-[11px]"
              >
                {item.name} ×{item.quantity}
              </span>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
