import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { auth } from "@/auth";
import { PlayerCollectionView } from "@/components/PlayerCollectionView";
import { ProfileHeader } from "@/components/ProfileHeader";
import { getEraCompletion, getPlayerCards } from "@/lib/db/cards";
import { getPlayerProfile } from "@/lib/db/players";
import {
  formatFallbackDisplayName,
  getStoredDisplayName,
  resolveDiscordUser,
} from "@/lib/discord-users";

export const dynamic = "force-dynamic";

export default async function PublicProfilePage({
  params,
}: {
  params: Promise<{ userId: string }>;
}) {
  const { userId } = await params;
  const session = await auth();

  let profile = null;
  let cards: ReturnType<typeof getPlayerCards> = [];
  let eraCompletion: ReturnType<typeof getEraCompletion> = [];
  let dbError: string | null = null;

  try {
    profile = getPlayerProfile(userId);
    if (profile && profile.existsInDb) {
      cards = getPlayerCards(userId);
      eraCompletion = getEraCompletion(userId);
    }
  } catch (err) {
    dbError =
      err instanceof Error
        ? err.message
        : "Could not read shared SQLite database.";
  }

  if (dbError) {
    return (
      <div className="space-y-6">
        <Link
          href="/leaderboard"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-400 transition hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Leaderboards
        </Link>
        <div className="rounded-2xl border border-rose-500/40 bg-rose-950/30 p-4 text-sm text-rose-200">
          <strong>Database Connection Notice:</strong> {dbError}
        </div>
      </div>
    );
  }

  if (!profile || !profile.existsInDb) {
    notFound();
  }

  const isOwnProfile = session?.user?.id === profile.userId;
  const discordUser = await resolveDiscordUser(profile.userId);
  const storedName = getStoredDisplayName(
    profile.displayName,
    profile.username
  );
  const displayName =
    storedName ??
    discordUser?.displayName ??
    (isOwnProfile ? session?.user?.name ?? null : null) ??
    formatFallbackDisplayName(profile.userId);
  const avatarUrl = isOwnProfile
    ? session?.user?.image ?? discordUser?.avatarUrl ?? null
    : discordUser?.avatarUrl ?? null;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between gap-4">
        <Link
          href="/leaderboard"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-400 transition hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Leaderboards
        </Link>
      </div>

      <ProfileHeader
        profile={profile}
        displayName={displayName}
        avatarUrl={avatarUrl}
        isOwnProfile={isOwnProfile}
      />

      <PlayerCollectionView cards={cards} eraCompletion={eraCompletion} />
    </div>
  );
}
