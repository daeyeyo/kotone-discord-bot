import { auth } from "@/auth";
import { LeaderboardClient } from "@/components/LeaderboardClient";
import {
  enrichLeaderboardWithDiscord,
  getLeaderboard,
  resolveDefaultEraForViewer,
  resolveDefaultMemberForViewer,
  type LeaderboardBoard,
  type LeaderboardKind,
} from "@/lib/db/leaderboards";

export const dynamic = "force-dynamic";

export default async function LeaderboardPage({
  searchParams,
}: {
  searchParams: Promise<{ board?: string; member?: string; era?: string }>;
}) {
  const params = await searchParams;
  const session = await auth();
  const viewerId = session?.user?.id || null;

  const rawBoard = params.board;
  const kind: LeaderboardKind =
    rawBoard === "member" || rawBoard === "era" || rawBoard === "global"
      ? rawBoard
      : params.member
      ? "member"
      : params.era
      ? "era"
      : "global";

  let board: LeaderboardBoard | null = null;
  let dbError: string | null = null;

  try {
    const memberCode =
      kind === "member"
        ? params.member || resolveDefaultMemberForViewer(viewerId)
        : null;
    const eraCode =
      kind === "era"
        ? params.era || resolveDefaultEraForViewer(viewerId)
        : null;

    const rawBoardObj = getLeaderboard({
      kind,
      memberCode,
      era: eraCode,
      viewerId,
    });
    board = await enrichLeaderboardWithDiscord(rawBoardObj, viewerId);
  } catch (err) {
    dbError =
      err instanceof Error
        ? err.message
        : "Could not read shared SQLite database.";
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-black tracking-tight text-white">
          Leaderboards
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          Global card counts, member specialists, and era completion rankings—matching{" "}
          <code className="font-mono text-pink-200">/leaderboard</code>.
        </p>
      </div>

      {dbError || !board ? (
        <div className="rounded-2xl border border-rose-500/40 bg-rose-950/30 p-4 text-sm text-rose-200">
          <strong>Database Connection Notice:</strong>{" "}
          {dbError ?? "Could not load leaderboard data."}
        </div>
      ) : (
        <LeaderboardClient board={board} viewerId={viewerId} />
      )}
    </div>
  );
}
