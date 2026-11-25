import {
  ERAS,
  ERA_ORDER,
  RARITY_ORDER,
  S_MEMBERS,
  S_ORDER,
} from "@/lib/catalog";
import {
  formatFallbackDisplayName,
  getStoredDisplayName,
  isSyntheticUserId,
  resolveDiscordUsers,
} from "@/lib/discord-users";
import {
  getReadOnlyDb,
  hasUsersDisplayNameColumn,
  parseSnowflake,
  toInt,
  toSnowflakeString,
} from "./client";

export type LeaderboardKind = "global" | "member" | "era";

export interface LeaderboardEntry {
  rank: number;
  userId: string;
  name: string;
  hasStoredName?: boolean;
  avatarUrl?: string | null;
  primary: string;
  secondary: string;
  value: number;
  tiebreakValue: number;
  complete: boolean;
}

export interface LeaderboardBoard {
  kind: LeaderboardKind;
  title: string;
  description: string;
  entries: LeaderboardEntry[];
  viewerEntry: LeaderboardEntry | null;
  chaseNote: string | null;
  emptyMessage: string;
  unrankedMessage: string;
  selectedMember?: string;
  selectedEra?: string;
}

interface UserCardAggregate {
  userId: string;
  userIdBigInt: bigint;
  username: string | null;
  displayName: string | null;
  groups: Array<{
    era: string;
    memberCode: string;
    rarity: string;
    copies: number;
  }>;
}

function pluralize(count: number, singular: string, plural?: string): string {
  if (count === 1) return `${count} ${singular}`;
  return `${count} ${plural ?? `${singular}s`}`;
}

function resolveAggregateNameFields(agg: UserCardAggregate): {
  name: string;
  hasStoredName: boolean;
} {
  const storedName = getStoredDisplayName(agg.displayName, agg.username);
  return {
    name: storedName ?? formatFallbackDisplayName(agg.userId),
    hasStoredName: Boolean(storedName),
  };
}

function loadAllPlayerAggregates(): UserCardAggregate[] {
  const db = getReadOnlyDb();
  const userSelect = hasUsersDisplayNameColumn(db)
    ? "SELECT user_id, username, display_name FROM users"
    : "SELECT user_id, username, NULL AS display_name FROM users";
  const userRows = db
    .prepare(userSelect)
    .all() as Array<{
    user_id: bigint;
    username: string | null;
    display_name: string | null;
  }>;
  const cardRows = db
    .prepare(
      `SELECT owner_id, era, member_code, rarity, COUNT(*) AS copies
       FROM cards
       WHERE owner_id IS NOT NULL
       GROUP BY owner_id, era, member_code, rarity`
    )
    .all() as Array<{
    owner_id: bigint;
    era: string;
    member_code: string;
    rarity: string;
    copies: bigint;
  }>;

  const statsMap = new Map<string, UserCardAggregate>();
  for (const u of userRows) {
    const idStr = toSnowflakeString(u.user_id);
    statsMap.set(idStr, {
      userId: idStr,
      userIdBigInt: u.user_id,
      username: u.username,
      displayName: u.display_name,
      groups: [],
    });
  }

  for (const row of cardRows) {
    const idStr = toSnowflakeString(row.owner_id);
    let agg = statsMap.get(idStr);
    if (!agg) {
      agg = {
        userId: idStr,
        userIdBigInt: row.owner_id,
        username: null,
        displayName: null,
        groups: [],
      };
      statsMap.set(idStr, agg);
    }
    agg.groups.push({
      era: row.era,
      memberCode: row.member_code,
      rarity: row.rarity,
      copies: toInt(row.copies),
    });
  }

  return Array.from(statsMap.values());
}

function computeChaseNote(
  entries: LeaderboardEntry[],
  viewerId: string | null,
  metric: string,
  tiebreakUnit: { singular: string; plural: string } = {
    singular: "copy",
    plural: "copies",
  }
): string | null {
  if (!viewerId) return null;
  const idx = entries.findIndex((e) => e.userId === viewerId);
  if (idx === -1) return null;
  if (idx === 0) return "You are #1 — defend your spot!";

  const viewer = entries[idx];
  const ahead = entries[idx - 1];
  const gap = ahead.value - viewer.value;
  if (gap > 0) {
    const unit = gap === 1 ? metric : `${metric}s`;
    return `${gap} ${unit} behind #${ahead.rank} ${ahead.name}.`;
  }

  const copyGap = ahead.tiebreakValue - viewer.tiebreakValue;
  if (copyGap > 0) {
    const unit = copyGap === 1 ? tiebreakUnit.singular : tiebreakUnit.plural;
    return `Tied with #${ahead.rank} ${ahead.name} on ${metric}s — ${copyGap} more ${unit} would pass them.`;
  }
  return `Tied with #${ahead.rank} ${ahead.name} — keep collecting!`;
}

function compareSnowflakeAsc(a: bigint, b: bigint): number {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

export function getLeaderboard(params: {
  kind: LeaderboardKind;
  memberCode?: string | null;
  era?: string | null;
  viewerId?: string | null;
}): LeaderboardBoard {
  const { kind, viewerId = null } = params;
  const aggregates = loadAllPlayerAggregates();

  if (kind === "member") {
    const memberCode =
      params.memberCode && params.memberCode in S_MEMBERS
        ? params.memberCode
        : "KTN";
    const memberName = S_MEMBERS[memberCode]?.name ?? memberCode;
    const memberEras = ERA_ORDER.filter(
      (eraKey) => memberCode in ERAS[eraKey].members
    );
    const totalSlots = memberEras.length * RARITY_ORDER.length;

    const scored = aggregates
      .map((agg) => {
        const matching = agg.groups.filter((g) => g.memberCode === memberCode);
        if (matching.length === 0) return null;
        const uniqueCount = matching.length;
        const totalCopies = matching.reduce((sum, g) => sum + g.copies, 0);
        return { agg, totalCopies, uniqueCount };
      })
      .filter((x): x is NonNullable<typeof x> => x !== null)
      .sort(
        (a, b) =>
          b.totalCopies - a.totalCopies ||
          b.uniqueCount - a.uniqueCount ||
          compareSnowflakeAsc(a.agg.userIdBigInt, b.agg.userIdBigInt)
      );

    const entries: LeaderboardEntry[] = scored.map((item, idx) => {
      const complete = item.uniqueCount >= totalSlots;
      const pct = totalSlots > 0 ? Math.round((item.uniqueCount / totalSlots) * 100) : 0;
      const nameFields = resolveAggregateNameFields(item.agg);
      return {
        rank: idx + 1,
        userId: item.agg.userId,
        ...nameFields,
        primary: pluralize(item.totalCopies, "card"),
        secondary: `${item.uniqueCount}/${totalSlots} unique (${pct}%)`,
        value: item.totalCopies,
        tiebreakValue: item.uniqueCount,
        complete,
      };
    });

    const viewerEntry = viewerId
      ? entries.find((e) => e.userId === viewerId) ?? null
      : null;

    return {
      kind: "member",
      selectedMember: memberCode,
      title: `Member Collection • ${memberName}`,
      description: `Ranked by total ${memberName} cards, including duplicates. Unique slots break ties across ${memberEras.length} ${memberEras.length === 1 ? "era" : "eras"} (${totalSlots} total slots).`,
      entries,
      viewerEntry,
      chaseNote: computeChaseNote(entries, viewerId, "member card", {
        singular: "unique card",
        plural: "unique cards",
      }),
      emptyMessage: `No one owns a ${memberName} card yet.`,
      unrankedMessage: `Collect a ${memberName} card to enter this leaderboard.`,
    };
  }

  if (kind === "era") {
    const era =
      params.era && params.era in ERAS ? params.era : "ASSEMBLE24";
    const eraName = ERAS[era].name;
    const totalSlots =
      Object.keys(ERAS[era].members).length * RARITY_ORDER.length;

    const scored = aggregates
      .map((agg) => {
        const matching = agg.groups.filter((g) => g.era === era);
        if (matching.length === 0) return null;
        const uniqueCount = matching.length;
        const totalCopies = matching.reduce((sum, g) => sum + g.copies, 0);
        return { agg, uniqueCount, totalCopies };
      })
      .filter((x): x is NonNullable<typeof x> => x !== null)
      .sort(
        (a, b) =>
          b.uniqueCount - a.uniqueCount ||
          b.totalCopies - a.totalCopies ||
          compareSnowflakeAsc(a.agg.userIdBigInt, b.agg.userIdBigInt)
      );

    const entries: LeaderboardEntry[] = scored.map((item, idx) => {
      const complete = item.uniqueCount >= totalSlots;
      const pct = totalSlots > 0 ? Math.round((item.uniqueCount / totalSlots) * 100) : 0;
      const nameFields = resolveAggregateNameFields(item.agg);
      return {
        rank: idx + 1,
        userId: item.agg.userId,
        ...nameFields,
        primary: `${item.uniqueCount}/${totalSlots} slots (${pct}%)`,
        secondary: pluralize(item.totalCopies, "copy", "copies"),
        value: item.uniqueCount,
        tiebreakValue: item.totalCopies,
        complete,
      };
    });

    const viewerEntry = viewerId
      ? entries.find((e) => e.userId === viewerId) ?? null
      : null;

    return {
      kind: "era",
      selectedEra: era,
      title: `Era Completion • ${eraName}`,
      description: `Ranked by unique (member, rarity) slots filled in ${eraName}. More copies break ties.`,
      entries,
      viewerEntry,
      chaseNote: computeChaseNote(entries, viewerId, "era slot"),
      emptyMessage: `No one owns a ${eraName} card yet.`,
      unrankedMessage: `Collect a ${eraName} card to enter Era Completion.`,
    };
  }

  // Global board
  const scored = aggregates
    .map((agg) => {
      const totalCards = agg.groups.reduce((sum, g) => sum + g.copies, 0);
      if (totalCards === 0) return null;
      const uniqueCount = agg.groups.length;
      return { agg, totalCards, uniqueCount };
    })
    .filter((x): x is NonNullable<typeof x> => x !== null)
    .sort(
      (a, b) =>
        b.totalCards - a.totalCards ||
        b.uniqueCount - a.uniqueCount ||
        compareSnowflakeAsc(a.agg.userIdBigInt, b.agg.userIdBigInt)
    );

  const entries: LeaderboardEntry[] = scored.map((item, idx) => ({
    rank: idx + 1,
    userId: item.agg.userId,
    ...resolveAggregateNameFields(item.agg),
    primary: pluralize(item.totalCards, "card"),
    secondary: pluralize(item.uniqueCount, "unique card"),
    value: item.totalCards,
    tiebreakValue: item.uniqueCount,
    complete: false,
  }));

  const viewerEntry = viewerId
    ? entries.find((e) => e.userId === viewerId) ?? null
    : null;

  return {
    kind: "global",
    title: "Global Card Collection",
    description:
      "Ranked by total cards owned across all servers, including duplicates. Unique cards break ties.",
    entries,
    viewerEntry,
    chaseNote: computeChaseNote(entries, viewerId, "card", {
      singular: "unique card",
      plural: "unique cards",
    }),
    emptyMessage: "No cards have been collected yet.",
    unrankedMessage: "Collect a card to enter the global leaderboard.",
  };
}

export function resolveDefaultMemberForViewer(userId: string | null): string {
  const id = parseSnowflake(userId);
  if (id === null) return "KTN";
  try {
    const db = getReadOnlyDb();
    const target = db
      .prepare("SELECT member_code FROM user_targets WHERE user_id = ?")
      .get(id) as { member_code: string } | undefined;
    if (target && target.member_code in S_MEMBERS) return target.member_code;

    const biases = db
      .prepare("SELECT member_code FROM user_biases WHERE user_id = ?")
      .all(id) as Array<{ member_code: string }>;
    const biasSet = new Set(biases.map((b) => b.member_code));
    for (const code of S_ORDER) {
      if (biasSet.has(code)) return code;
    }

    const top = db
      .prepare(
        `SELECT member_code, COUNT(*) AS cnt
         FROM cards WHERE owner_id = ?
         GROUP BY member_code ORDER BY cnt DESC LIMIT 1`
      )
      .get(id) as { member_code: string; cnt: bigint } | undefined;
    if (top && top.member_code in S_MEMBERS) return top.member_code;
  } catch {
    return "KTN";
  }
  return "KTN";
}

export function resolveDefaultEraForViewer(userId: string | null): string {
  const id = parseSnowflake(userId);
  if (id === null) return "ASSEMBLE24";
  try {
    const db = getReadOnlyDb();
    const target = db
      .prepare("SELECT era FROM user_targets WHERE user_id = ?")
      .get(id) as { era: string | null } | undefined;
    if (target?.era && target.era in ERAS) return target.era;

    const top = db
      .prepare(
        `SELECT era, COUNT(*) AS cnt
         FROM cards WHERE owner_id = ?
         GROUP BY era ORDER BY cnt DESC LIMIT 1`
      )
      .get(id) as { era: string; cnt: bigint } | undefined;
    if (top && top.era in ERAS) return top.era;
  } catch {
    return "ASSEMBLE24";
  }
  return "ASSEMBLE24";
}

function metricForKind(kind: LeaderboardKind): string {
  if (kind === "member") return "member card";
  if (kind === "era") return "era slot";
  return "card";
}

function tiebreakUnitForKind(kind: LeaderboardKind): {
  singular: string;
  plural: string;
} {
  if (kind === "era") {
    return { singular: "copy", plural: "copies" };
  }
  return { singular: "unique card", plural: "unique cards" };
}

export async function enrichLeaderboardWithDiscord(
  board: LeaderboardBoard,
  viewerId: string | null = null,
  options?: { limit?: number }
): Promise<LeaderboardBoard> {
  if (board.entries.length === 0) return board;

  const targetEntries =
    options?.limit !== undefined
      ? board.entries.slice(0, options.limit)
      : board.entries;
  const targetIdSet = new Set(targetEntries.map((entry) => entry.userId));

  if (viewerId) {
    const viewerIndex = board.entries.findIndex((e) => e.userId === viewerId);
    if (viewerIndex !== -1) {
      targetIdSet.add(board.entries[viewerIndex].userId);
      if (viewerIndex > 0) {
        targetIdSet.add(board.entries[viewerIndex - 1].userId);
      }
    }
  }

  const priorityIds = board.entries
    .filter(
      (entry) =>
        targetIdSet.has(entry.userId) &&
        !entry.hasStoredName &&
        !isSyntheticUserId(entry.userId)
    )
    .map((entry) => entry.userId);

  const discordMap = await resolveDiscordUsers(Array.from(targetIdSet), {
    priorityIds,
  });

  const enrichedEntries = board.entries.map((entry) => {
    const discordUser = discordMap.get(entry.userId);
    if (!discordUser) return entry;
    return {
      ...entry,
      name: entry.hasStoredName
        ? entry.name
        : discordUser.displayName || entry.name,
      avatarUrl: discordUser.avatarUrl ?? entry.avatarUrl ?? null,
    };
  });

  const viewerEntry = viewerId
    ? enrichedEntries.find((e) => e.userId === viewerId) ?? null
    : null;

  return {
    ...board,
    entries: enrichedEntries,
    viewerEntry,
    chaseNote: computeChaseNote(
      enrichedEntries,
      viewerId,
      metricForKind(board.kind),
      tiebreakUnitForKind(board.kind)
    ),
  };
}
