"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle2, Crown, Globe, Heart, Layers, Medal } from "lucide-react";
import { ERAS, ERA_ORDER, S_MEMBERS, S_ORDER } from "@/lib/catalog";
import type { LeaderboardBoard, LeaderboardKind } from "@/lib/db/leaderboards";

interface LeaderboardClientProps {
  board: LeaderboardBoard;
  viewerId: string | null;
}

export function LeaderboardClient({
  board,
  viewerId,
}: LeaderboardClientProps) {
  const router = useRouter();

  const navigate = (
    kind: LeaderboardKind,
    member?: string,
    era?: string
  ) => {
    const params = new URLSearchParams();
    params.set("board", kind);
    if (kind === "member" && member) params.set("member", member);
    if (kind === "era" && era) params.set("era", era);
    router.push(`/leaderboard?${params.toString()}`);
  };

  return (
    <div className="space-y-6">
      {/* Board Switcher + Filters */}
      <div className="flex flex-col justify-between gap-4 rounded-3xl border border-white/10 bg-[#10101a]/90 p-5 sm:flex-row sm:items-center">
        <div className="inline-flex flex-wrap rounded-2xl border border-white/10 bg-black/40 p-1">
          <button
            type="button"
            onClick={() => navigate("global")}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition ${
              board.kind === "global"
                ? "bg-[#ff6b8b] text-white shadow-[0_0_20px_-4px_rgba(255,107,139,0.7)]"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            <Globe className="h-4 w-4" />
            Global Cards
          </button>
          <button
            type="button"
            onClick={() => navigate("member", board.selectedMember ?? "KTN")}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition ${
              board.kind === "member"
                ? "bg-[#ff6b8b] text-white shadow-[0_0_20px_-4px_rgba(255,107,139,0.7)]"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            <Heart className="h-4 w-4" />
            Member
          </button>
          <button
            type="button"
            onClick={() => navigate("era", undefined, board.selectedEra ?? "ASSEMBLE24")}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition ${
              board.kind === "era"
                ? "bg-[#ff6b8b] text-white shadow-[0_0_20px_-4px_rgba(255,107,139,0.7)]"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            <Layers className="h-4 w-4" />
            Era Completion
          </button>
        </div>

        {board.kind === "member" && (
          <select
            value={board.selectedMember ?? "KTN"}
            onChange={(e) => navigate("member", e.target.value)}
            className="h-10 rounded-xl border border-white/10 bg-black/40 px-3 text-sm text-white focus:border-[#ff6b8b]/60 focus:outline-none"
          >
            {S_ORDER.map((code, idx) => (
              <option key={code} value={code}>
                S{idx + 1} • {S_MEMBERS[code]?.name ?? code} (
                {S_MEMBERS[code]?.full_name})
              </option>
            ))}
          </select>
        )}

        {board.kind === "era" && (
          <select
            value={board.selectedEra ?? "ASSEMBLE24"}
            onChange={(e) => navigate("era", undefined, e.target.value)}
            className="h-10 rounded-xl border border-white/10 bg-black/40 px-3 text-sm text-white focus:border-[#ff6b8b]/60 focus:outline-none"
          >
            {ERA_ORDER.map((eraKey) => (
              <option key={eraKey} value={eraKey}>
                {ERAS[eraKey].name}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Board Header + Viewer Chase Banner */}
      <div className="rounded-3xl border border-white/10 bg-[#10101a]/90 p-6">
        <h2 className="text-xl font-extrabold text-white">{board.title}</h2>
        <p className="mt-1 text-sm text-zinc-400">{board.description}</p>

        {viewerId && (
          <div className="mt-4 rounded-2xl border border-[#ff6b8b]/30 bg-[#ff6b8b]/10 px-4 py-3 text-sm text-pink-100">
            {board.viewerEntry ? (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  Your rank:{" "}
                  <strong className="text-white">
                    #{board.viewerEntry.rank}
                  </strong>{" "}
                  ({board.viewerEntry.primary} • {board.viewerEntry.secondary})
                </span>
                {board.chaseNote && (
                  <span className="font-medium text-[#ff9bb0]">
                    {board.chaseNote}
                  </span>
                )}
              </div>
            ) : (
              <span>{board.unrankedMessage}</span>
            )}
          </div>
        )}

        {/* Rankings Table */}
        {board.entries.length === 0 ? (
          <div className="mt-6 rounded-2xl border border-dashed border-white/10 py-12 text-center text-sm text-zinc-400">
            {board.emptyMessage}
          </div>
        ) : (
          <div className="mt-6 divide-y divide-white/5 overflow-hidden rounded-2xl border border-white/10 bg-black/30">
            {board.entries.map((entry) => {
              const isViewer = viewerId === entry.userId;
              const isTop3 = entry.rank <= 3;

              return (
                <Link
                  key={entry.userId}
                  href={`/profile/${entry.userId}`}
                  className={`flex items-center justify-between gap-4 px-4 py-3.5 transition hover:bg-white/[0.04] sm:px-5 ${
                    isViewer ? "bg-[#ff6b8b]/10" : ""
                  }`}
                >
                  <div className="flex min-w-0 items-center gap-3.5">
                    <div
                      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl font-mono text-sm font-extrabold ${
                        entry.rank === 1
                          ? "bg-amber-400/20 text-amber-300 ring-1 ring-amber-400/50"
                          : entry.rank === 2
                          ? "bg-slate-300/15 text-slate-200 ring-1 ring-slate-300/40"
                          : entry.rank === 3
                          ? "bg-orange-400/15 text-orange-300 ring-1 ring-orange-400/40"
                          : "bg-white/5 text-zinc-400"
                      }`}
                    >
                      {entry.rank === 1 ? (
                        <Crown className="h-4 w-4" />
                      ) : isTop3 ? (
                        <Medal className="h-4 w-4" />
                      ) : (
                        `#${entry.rank}`
                      )}
                    </div>

                    {entry.avatarUrl ? (
                      <img
                        src={entry.avatarUrl}
                        alt={entry.name}
                        className="h-9 w-9 shrink-0 rounded-full object-cover ring-1 ring-white/15"
                      />
                    ) : (
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#ff6b8b]/30 to-violet-500/30 text-xs font-bold text-white ring-1 ring-white/15">
                        {entry.name[0]?.toUpperCase() ?? "K"}
                      </span>
                    )}

                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-bold text-white">
                          {entry.name}
                        </span>
                        {isViewer && (
                          <span className="rounded-md bg-[#ff6b8b]/20 px-1.5 py-0.5 text-[10px] font-bold text-[#ff9bb0]">
                            YOU
                          </span>
                        )}
                        {entry.complete && (
                          <span className="inline-flex items-center gap-1 rounded-md border border-emerald-400/40 bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">
                            <CheckCircle2 className="h-3 w-3" />
                            Complete
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-zinc-500">
                        View binder & era progress →
                      </p>
                    </div>
                  </div>

                  <div className="shrink-0 text-right">
                    <p className="text-sm font-bold text-white">
                      {entry.primary}
                    </p>
                    <p className="text-xs text-zinc-400">{entry.secondary}</p>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
