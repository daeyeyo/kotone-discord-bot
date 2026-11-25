import {
  CATALOG,
  ERAS,
  RARITY_ORDER,
  SHOP_ITEMS,
  S_MEMBERS,
  S_ORDER,
} from "@/lib/catalog";
import {
  getReadOnlyDb,
  hasUsersDisplayNameColumn,
  parseSnowflake,
  toInt,
} from "./client";

export interface ActiveCooldown {
  type: string;
  expiresAt: number;
  remainingSeconds: number;
}

export interface PlayerItem {
  key: string;
  name: string;
  description: string;
  quantity: number;
}

export interface PlayerProfile {
  userId: string;
  existsInDb: boolean;
  username: string | null;
  displayName: string | null;
  como: number;
  dailyStreak: number;
  lastDaily: string | null;
  bio: string | null;
  biases: string[];
  target: {
    era: string | null;
    memberCode: string;
    rarity: string | null;
    label: string;
  } | null;
  totalCards: number;
  uniqueCards: number;
  binderCards: number;
  listedCards: number;
  rarityCounts: Record<string, number>;
  eraCounts: Record<string, number>;
  activeBoosterExpiresAt: number | null;
  cooldowns: ActiveCooldown[];
  items: PlayerItem[];
  effects: {
    mergeDiscounts: number;
    streakShields: number;
    extraDropSlots: number;
  };
  spinsUsedToday: number;
  spinDailyLimit: number;
}

export interface CommunitySummary {
  totalPlayers: number;
  totalCards: number;
  totalMarketListings: number;
  totalComo: number;
}

function formatTargetLabel(
  era: string | null,
  memberCode: string,
  rarity: string | null
): string {
  const memberName =
    (era ? ERAS[era]?.members?.[memberCode]?.name : undefined) ??
    S_MEMBERS[memberCode]?.name ??
    memberCode;
  const parts: string[] = [];
  if (rarity) parts.push(rarity);
  parts.push(memberName);
  if (era) parts.push(`(${ERAS[era]?.name ?? era})`);
  return parts.join(" ");
}

function getLocalIsoDate(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function getCommunitySummary(): CommunitySummary {
  const db = getReadOnlyDb();
  const playersRow = db
    .prepare("SELECT COUNT(*) AS count, COALESCE(SUM(como), 0) AS total_como FROM users")
    .get() as { count: bigint; total_como: bigint } | undefined;
  const cardsRow = db
    .prepare("SELECT COUNT(*) AS count FROM cards WHERE owner_id IS NOT NULL")
    .get() as { count: bigint } | undefined;
  const marketRow = db
    .prepare("SELECT COUNT(*) AS count FROM market_listings")
    .get() as { count: bigint } | undefined;

  return {
    totalPlayers: toInt(playersRow?.count),
    totalCards: toInt(cardsRow?.count),
    totalMarketListings: toInt(marketRow?.count),
    totalComo: toInt(playersRow?.total_como),
  };
}

export function getPlayerProfile(userId: string): PlayerProfile | null {
  const snowflake = parseSnowflake(userId);
  if (snowflake === null) return null;

  const db = getReadOnlyDb();
  const nowSec = Date.now() / 1000;

  const userSelect = hasUsersDisplayNameColumn(db)
    ? "SELECT user_id, username, display_name, daily_streak, last_daily, como FROM users WHERE user_id = ?"
    : "SELECT user_id, username, NULL AS display_name, daily_streak, last_daily, como FROM users WHERE user_id = ?";
  const userRow = db
    .prepare(userSelect)
    .get(snowflake) as
    | {
        user_id: bigint;
        username: string | null;
        display_name: string | null;
        daily_streak: bigint | null;
        last_daily: string | null;
        como: bigint | null;
      }
    | undefined;

  const bioRow = db
    .prepare("SELECT bio FROM user_bios WHERE user_id = ?")
    .get(snowflake) as { bio: string } | undefined;

  const biasRows = db
    .prepare("SELECT member_code FROM user_biases WHERE user_id = ?")
    .all(snowflake) as Array<{ member_code: string }>;
  const biasSet = new Set(biasRows.map((r) => r.member_code));
  const biases = S_ORDER.filter((code) => biasSet.has(code));

  const targetRow = db
    .prepare("SELECT era, member_code, rarity FROM user_targets WHERE user_id = ?")
    .get(snowflake) as
    | { era: string | null; member_code: string; rarity: string | null }
    | undefined;

  const cardAgg = db
    .prepare(
      `SELECT
         COUNT(*) AS total_cards,
         SUM(CASE WHEN in_binder = 1 THEN 1 ELSE 0 END) AS binder_cards
       FROM cards
       WHERE owner_id = ?`
    )
    .get(snowflake) as
    | { total_cards: bigint; binder_cards: bigint | null }
    | undefined;

  const uniqueAgg = db
    .prepare(
      `SELECT COUNT(*) AS unique_cards FROM (
         SELECT DISTINCT era, member_code, rarity
         FROM cards
         WHERE owner_id = ?
       )`
    )
    .get(snowflake) as { unique_cards: bigint } | undefined;

  const listedAgg = db
    .prepare("SELECT COUNT(*) AS count FROM market_listings WHERE seller_id = ?")
    .get(snowflake) as { count: bigint } | undefined;

  const rarityRows = db
    .prepare(
      "SELECT rarity, COUNT(*) AS count FROM cards WHERE owner_id = ? GROUP BY rarity"
    )
    .all(snowflake) as Array<{ rarity: string; count: bigint }>;
  const rarityCounts: Record<string, number> = Object.fromEntries(
    RARITY_ORDER.map((r) => [r, 0])
  );
  for (const row of rarityRows) {
    rarityCounts[row.rarity] = toInt(row.count);
  }

  const eraRows = db
    .prepare(
      "SELECT era, COUNT(*) AS count FROM cards WHERE owner_id = ? GROUP BY era"
    )
    .all(snowflake) as Array<{ era: string; count: bigint }>;
  const eraCounts: Record<string, number> = {};
  for (const row of eraRows) {
    eraCounts[row.era] = toInt(row.count);
  }

  const boosterRow = db
    .prepare("SELECT expires_at FROM user_drop_boosters WHERE user_id = ?")
    .get(snowflake) as { expires_at: number } | undefined;
  const activeBoosterExpiresAt =
    boosterRow && boosterRow.expires_at > nowSec ? boosterRow.expires_at : null;

  const cooldownRows = db
    .prepare(
      "SELECT cooldown_type, expires_at FROM cooldowns WHERE user_id = ? AND expires_at > ? ORDER BY expires_at ASC"
    )
    .all(snowflake, nowSec) as Array<{
    cooldown_type: string;
    expires_at: number;
  }>;
  const cooldowns: ActiveCooldown[] = cooldownRows.map((row) => ({
    type: row.cooldown_type,
    expiresAt: row.expires_at,
    remainingSeconds: Math.max(0, Math.floor(row.expires_at - nowSec)),
  }));

  const itemRows = db
    .prepare(
      "SELECT item_key, quantity FROM user_items WHERE user_id = ? AND quantity > 0 ORDER BY item_key"
    )
    .all(snowflake) as Array<{ item_key: string; quantity: bigint }>;
  const items: PlayerItem[] = itemRows
    .filter((row) => row.item_key in SHOP_ITEMS)
    .map((row) => ({
      key: row.item_key,
      name: SHOP_ITEMS[row.item_key].name,
      description: SHOP_ITEMS[row.item_key].description,
      quantity: toInt(row.quantity),
    }));

  const effectsRow = db
    .prepare(
      "SELECT merge_discounts, streak_shields, extra_drop_slots FROM user_item_effects WHERE user_id = ?"
    )
    .get(snowflake) as
    | {
        merge_discounts: bigint;
        streak_shields: bigint;
        extra_drop_slots: bigint;
      }
    | undefined;

  const todayIso = getLocalIsoDate();
  const spinRow = db
    .prepare("SELECT spin_date, spins FROM spin_usage WHERE user_id = ?")
    .get(snowflake) as { spin_date: string; spins: bigint } | undefined;
  const spinsUsedToday =
    spinRow && spinRow.spin_date === todayIso ? toInt(spinRow.spins) : 0;

  const totalCards = toInt(cardAgg?.total_cards);
  const existsInDb = Boolean(userRow) || totalCards > 0;

  return {
    userId: snowflake.toString(),
    existsInDb,
    username: userRow?.username ?? null,
    displayName: userRow?.display_name ?? null,
    como: toInt(userRow?.como),
    dailyStreak: toInt(userRow?.daily_streak),
    lastDaily: userRow?.last_daily ?? null,
    bio: bioRow?.bio ?? null,
    biases,
    target: targetRow
      ? {
          era: targetRow.era,
          memberCode: targetRow.member_code,
          rarity: targetRow.rarity,
          label: formatTargetLabel(
            targetRow.era,
            targetRow.member_code,
            targetRow.rarity
          ),
        }
      : null,
    totalCards,
    uniqueCards: toInt(uniqueAgg?.unique_cards),
    binderCards: toInt(cardAgg?.binder_cards),
    listedCards: toInt(listedAgg?.count),
    rarityCounts,
    eraCounts,
    activeBoosterExpiresAt,
    cooldowns,
    items,
    effects: {
      mergeDiscounts: toInt(effectsRow?.merge_discounts),
      streakShields: toInt(effectsRow?.streak_shields),
      extraDropSlots: toInt(effectsRow?.extra_drop_slots),
    },
    spinsUsedToday,
    spinDailyLimit: CATALOG.spinDailyLimit,
  };
}
