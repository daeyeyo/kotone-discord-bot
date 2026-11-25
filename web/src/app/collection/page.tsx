import Link from "next/link";
import { ArrowRight, Lock, Sparkles } from "lucide-react";
import { auth, isDiscordAuthConfigured, signInWithDiscord } from "@/auth";
import { PlayerCollectionView } from "@/components/PlayerCollectionView";
import { ProfileHeader } from "@/components/ProfileHeader";
import { getEraCompletion, getPlayerCards } from "@/lib/db/cards";
import { getPlayerProfile } from "@/lib/db/players";
import {
  formatFallbackDisplayName,
  getStoredDisplayName,
} from "@/lib/player-names";

export const dynamic = "force-dynamic";

export default async function CollectionPage() {
  const session = await auth();
  const user = session?.user;

  if (!user?.id) {
    return (
      <div className="mx-auto max-w-2xl py-10">
        <div className="rounded-3xl border border-white/10 bg-[#10101a]/95 p-8 text-center shadow-2xl">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[#ff6b8b]/15 text-[#ff6b8b] ring-1 ring-[#ff6b8b]/30">
            <Lock className="h-6 w-6" />
          </div>
          <h1 className="mt-4 text-2xl font-extrabold text-white">
            Sign in to View Your Photocard Binder
          </h1>
          <p className="mt-2 text-sm text-zinc-300">
            Connect with Discord so we can match your Discord ID to your Kotone
            Bot inventory, COMO balance, and era completion.
          </p>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            {isDiscordAuthConfigured ? (
              <form
                action={async () => {
                  "use server";
                  await signInWithDiscord("/collection");
                }}
              >
                <button
                  type="submit"
                  className="inline-flex items-center gap-2 rounded-xl bg-[#5865F2] px-5 py-2.5 text-sm font-bold text-white transition hover:bg-[#4752C4]"
                >
                  Login with Discord
                  <ArrowRight className="h-4 w-4" />
                </button>
              </form>
            ) : (
              <Link
                href="/login"
                className="inline-flex items-center gap-2 rounded-xl bg-[#5865F2] px-5 py-2.5 text-sm font-bold text-white transition hover:bg-[#4752C4]"
              >
                Setup Discord Login
                <ArrowRight className="h-4 w-4" />
              </Link>
            )}

            <Link
              href="/leaderboard"
              className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/5 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-white/10"
            >
              Preview Player Profiles via Leaderboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  let profile = null;
  let cards: ReturnType<typeof getPlayerCards> = [];
  let eraCompletion: ReturnType<typeof getEraCompletion> = [];
  let dbError: string | null = null;

  try {
    profile = getPlayerProfile(user.id);
    if (profile) {
      cards = getPlayerCards(user.id);
      eraCompletion = getEraCompletion(user.id);
    }
  } catch (err) {
    dbError =
      err instanceof Error
        ? err.message
        : "Could not read shared SQLite database.";
  }

  if (dbError) {
    return (
      <div className="rounded-2xl border border-rose-500/40 bg-rose-950/30 p-4 text-sm text-rose-200">
        <strong>Database Connection Notice:</strong> {dbError}
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="rounded-3xl border border-white/10 bg-[#10101a] p-8 text-center">
        <p className="text-lg font-bold text-white">Invalid Discord Session</p>
        <p className="mt-1 text-sm text-zinc-400">
          Please sign out and sign back in with Discord.
        </p>
      </div>
    );
  }

  const resolvedDisplayName =
    getStoredDisplayName(profile.displayName, profile.username) ??
    user.name ??
    user.username ??
    formatFallbackDisplayName(profile.userId);

  return (
    <div className="space-y-8">
      <ProfileHeader
        profile={profile}
        displayName={resolvedDisplayName}
        avatarUrl={user.image}
        isOwnProfile
      />

      {!profile.existsInDb ? (
        <div className="rounded-3xl border border-dashed border-white/15 bg-[#10101a]/80 p-10 text-center">
          <Sparkles className="mx-auto h-8 w-8 text-[#ff6b8b]" />
          <h2 className="mt-3 text-xl font-bold text-white">
            No Kotone Bot Profile Found Yet
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-zinc-400">
            Use <code className="font-mono text-pink-200">/daily</code> or{" "}
            <code className="font-mono text-pink-200">/drop</code> in Discord
            with Kotone Bot to start collecting photocards—your binder will
            appear here automatically.
          </p>
        </div>
      ) : (
        <PlayerCollectionView cards={cards} eraCompletion={eraCompletion} />
      )}
    </div>
  );
}
