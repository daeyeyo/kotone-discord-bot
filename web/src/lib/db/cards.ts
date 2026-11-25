import {
  ERAS,
  ERA_ORDER,
  MEMBER_SPECIALTY,
  RARITY_ABILITY_ROLLS,
  RARITY_ORDER,
  getAnimatedCardImage,
  getCardImage,
  getMemberDisplay,
  getRarityMeta,
} from "@/lib/catalog";
import { getReadOnlyDb, parseSnowflake, toInt } from "./client";

export interface OwnedCard {
  id: number;
  serial: string;
  memberCode: string;
  memberName: string;
  memberFullName: string;
  sNumber: string;
  era: string;
  eraName: string;
  rarity: string;
  rarityRank: number;
  obtainedAt: string | null;
  inBinder: boolean;
  marketPrice: number | null;
  listedAt: string | null;
  skill: string;
  skillPoints: number | null;
  skillCap: number;
  trainingSessions: number;
  performances: number;
  lastTrained: number | null;
  imageUrl: string | null;
  animatedUrl: string | null;
  copyCount: number;
}

export interface EraRarityProgress {
  rarity: string;
  ownedCount: number;
  totalMembers: number;
  ownedMemberCodes: string[];
  copyCountsByMember: Record<string, number>;
}

export interface EraCompletionSummary {
  era: string;
  eraName: string;
  totalMembers: number;
  totalSlots: number;
  ownedSlots: number;
  totalCopies: number;
  percentage: number;
  byRarity: Record<string, EraRarityProgress>;
}

export function getPlayerCards(userId: string): OwnedCard[] {
  const snowflake = parseSnowflake(userId);
  if (snowflake === null) return [];

  const db = getReadOnlyDb();
  const rows = db
    .prepare(
      `SELECT
         c.id,
         c.serial,
         c.member_code,
         c.era,
         c.rarity,
         c.obtained_at,
         c.in_binder,
         s.skill,
         s.points,
         s.training_sessions,
         s.performances,
         s.last_trained,
         m.price AS market_price,
         m.listed_at AS listed_at
       FROM cards c
       LEFT JOIN card_skill_points s ON c.serial = s.card_serial
       LEFT JOIN market_listings m ON c.serial = m.card_serial
       WHERE c.owner_id = ?
       ORDER BY c.id DESC`
    )
    .all(snowflake) as Array<{
    id: bigint;
    serial: string;
    member_code: string;
    era: string;
    rarity: string;
    obtained_at: string | null;
    in_binder: bigint;
    skill: string | null;
    points: bigint | null;
    training_sessions: bigint | null;
    performances: bigint | null;
    last_trained: number | null;
    market_price: bigint | null;
    listed_at: string | null;
  }>;

  const groupCounts = new Map<string, number>();
  for (const row of rows) {
    const key = `${row.era}|${row.member_code}|${row.rarity}`;
    groupCounts.set(key, (groupCounts.get(key) ?? 0) + 1);
  }

  return rows.map((row) => {
    const display = getMemberDisplay(row.era, row.member_code);
    const rarityMeta = getRarityMeta(row.rarity);
    const cap =
      RARITY_ABILITY_ROLLS[row.rarity]?.cap ??
      RARITY_ABILITY_ROLLS.Common.cap;
    const key = `${row.era}|${row.member_code}|${row.rarity}`;

    return {
      id: toInt(row.id),
      serial: row.serial,
      memberCode: row.member_code,
      memberName: display.name,
      memberFullName: display.fullName,
      sNumber: display.sNumber,
      era: row.era,
      eraName: display.eraName,
      rarity: row.rarity,
      rarityRank: rarityMeta.rank,
      obtainedAt: row.obtained_at,
      inBinder: toInt(row.in_binder) === 1,
      marketPrice: row.market_price !== null ? toInt(row.market_price) : null,
      listedAt: row.listed_at,
      skill: row.skill ?? MEMBER_SPECIALTY[row.member_code] ?? "Vocals",
      skillPoints: row.points !== null ? toInt(row.points) : null,
      skillCap: cap,
      trainingSessions: toInt(row.training_sessions),
      performances: toInt(row.performances),
      lastTrained: row.last_trained,
      imageUrl: getCardImage(row.era, row.member_code, row.rarity, false),
      animatedUrl: getAnimatedCardImage(row.era, row.member_code, row.rarity),
      copyCount: groupCounts.get(key) ?? 1,
    };
  });
}

export function getEraCompletion(userId: string): EraCompletionSummary[] {
  const snowflake = parseSnowflake(userId);
  const countsMap = new Map<string, number>();

  if (snowflake !== null) {
    const db = getReadOnlyDb();
    const rows = db
      .prepare(
        `SELECT era, member_code, rarity, COUNT(*) AS copies
         FROM cards
         WHERE owner_id = ?
         GROUP BY era, member_code, rarity`
      )
      .all(snowflake) as Array<{
      era: string;
      member_code: string;
      rarity: string;
      copies: bigint;
    }>;

    for (const row of rows) {
      countsMap.set(
        `${row.era}|${row.member_code}|${row.rarity}`,
        toInt(row.copies)
      );
    }
  }

  return ERA_ORDER.map((era) => {
    const eraData = ERAS[era];
    const memberCodes = Object.keys(eraData.members);
    const totalMembers = memberCodes.length;
    const totalSlots = totalMembers * RARITY_ORDER.length;

    let ownedSlots = 0;
    let totalCopies = 0;
    const byRarity: Record<string, EraRarityProgress> = {};

    for (const rarity of RARITY_ORDER) {
      const ownedMemberCodes: string[] = [];
      const copyCountsByMember: Record<string, number> = {};

      for (const memberCode of memberCodes) {
        const copies = countsMap.get(`${era}|${memberCode}|${rarity}`) ?? 0;
        if (copies > 0) {
          ownedMemberCodes.push(memberCode);
          copyCountsByMember[memberCode] = copies;
          ownedSlots += 1;
          totalCopies += copies;
        }
      }

      byRarity[rarity] = {
        rarity,
        ownedCount: ownedMemberCodes.length,
        totalMembers,
        ownedMemberCodes,
        copyCountsByMember,
      };
    }

    return {
      era,
      eraName: eraData.name,
      totalMembers,
      totalSlots,
      ownedSlots,
      totalCopies,
      percentage: totalSlots > 0 ? Math.round((ownedSlots / totalSlots) * 100) : 0,
      byRarity,
    };
  });
}
