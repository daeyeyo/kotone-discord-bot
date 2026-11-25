import catalogData from "@/data/catalog.json";

export interface MemberEntry {
  name: string;
  full_name: string;
  images: Record<string, string>;
  animated_images?: Record<string, string>;
}

export interface EraEntry {
  name: string;
  members: Record<string, MemberEntry>;
}

export interface ShopItemEntry {
  name: string;
  price: number;
  description: string;
}

export interface CatalogShape {
  eras: Record<string, EraEntry>;
  eraOrder: string[];
  eraAliases: Record<string, string[]>;
  rarities: Record<string, number>;
  rarityOrder: string[];
  rarityAbilityRolls: Record<string, { specialty: [number, number]; cap: number }>;
  sOrder: string[];
  sMembers: Record<string, { name: string; full_name: string }>;
  memberSpecialty: Record<string, string>;
  spinDailyLimit: number;
  cooldownDurations: Record<string, number>;
  shopItems: Record<string, ShopItemEntry>;
  dropBoosterDuration: number;
  dropBoosterRarityMultiplier: number;
}

export const CATALOG = catalogData as unknown as CatalogShape;
export const ERAS = CATALOG.eras;
export const ERA_ORDER = CATALOG.eraOrder;
export const RARITY_ORDER = CATALOG.rarityOrder;
export const RARITY_ABILITY_ROLLS = CATALOG.rarityAbilityRolls;
export const S_ORDER = CATALOG.sOrder;
export const S_MEMBERS = CATALOG.sMembers;
export const MEMBER_SPECIALTY = CATALOG.memberSpecialty;
export const SHOP_ITEMS = CATALOG.shopItems;

export interface RarityMeta {
  name: string;
  rank: number;
  textClass: string;
  badgeClass: string;
  borderClass: string;
  glowClass: string;
  barClass: string;
  accentHex: string;
  isHolo: boolean;
}

const RARITY_STYLES: Record<string, Omit<RarityMeta, "name" | "rank">> = {
  Common: {
    textClass: "text-slate-300",
    badgeClass: "bg-slate-800/90 text-slate-200 border-slate-600/60",
    borderClass: "border-slate-700/80 hover:border-slate-500/80",
    glowClass: "",
    barClass: "bg-slate-400",
    accentHex: "#94a3b8",
    isHolo: false,
  },
  Rare: {
    textClass: "text-sky-300",
    badgeClass: "bg-sky-950/90 text-sky-200 border-sky-500/50",
    borderClass: "border-sky-500/45 hover:border-sky-400/80",
    glowClass: "shadow-[0_0_24px_-8px_rgba(56,189,248,0.45)]",
    barClass: "bg-sky-400",
    accentHex: "#38bdf8",
    isHolo: false,
  },
  Epic: {
    textClass: "text-violet-300",
    badgeClass: "bg-violet-950/90 text-violet-200 border-violet-500/55",
    borderClass: "border-violet-500/55 hover:border-violet-400/90",
    glowClass: "shadow-[0_0_28px_-6px_rgba(167,139,250,0.55)]",
    barClass: "bg-violet-400",
    accentHex: "#a78bfa",
    isHolo: true,
  },
  Legendary: {
    textClass: "text-amber-300",
    badgeClass: "bg-amber-950/90 text-amber-200 border-amber-400/65",
    borderClass: "border-amber-400/65 hover:border-amber-300",
    glowClass: "shadow-[0_0_32px_-6px_rgba(251,191,36,0.55)]",
    barClass: "bg-amber-400",
    accentHex: "#fbbf24",
    isHolo: true,
  },
  Mythic: {
    textClass: "text-pink-300",
    badgeClass:
      "bg-gradient-to-r from-pink-950/95 via-fuchsia-950/95 to-cyan-950/95 text-pink-100 border-pink-400/75",
    borderClass: "border-pink-400/75 hover:border-pink-300",
    glowClass: "shadow-[0_0_36px_-4px_rgba(255,107,139,0.7)]",
    barClass: "bg-gradient-to-r from-pink-400 via-fuchsia-400 to-cyan-400",
    accentHex: "#ff6b8b",
    isHolo: true,
  },
};

export function getRarityMeta(rarity: string): RarityMeta {
  const rank = RARITY_ORDER.indexOf(rarity);
  const style = RARITY_STYLES[rarity] ?? RARITY_STYLES.Common;
  return {
    name: rarity,
    rank: rank === -1 ? 0 : rank,
    ...style,
  };
}

export function getCardImage(
  era: string,
  memberCode: string,
  rarity: string,
  animated = false
): string | null {
  const member = ERAS[era]?.members?.[memberCode];
  if (!member) return null;

  if (animated) {
    const animatedUrl = member.animated_images?.[rarity];
    if (animatedUrl && !animatedUrl.includes("example.com")) {
      return animatedUrl;
    }
  }

  let url = member.images?.[rarity];
  if (!url && rarity === "Mythic") {
    url = member.images?.["Legendary"];
  }
  if (!url || url.includes("example.com")) {
    return null;
  }
  return url;
}

export function getAnimatedCardImage(
  era: string,
  memberCode: string,
  rarity: string
): string | null {
  const url = ERAS[era]?.members?.[memberCode]?.animated_images?.[rarity];
  if (!url || url.includes("example.com")) {
    return null;
  }
  return url;
}

export function getMemberNumber(memberCode: string): string {
  const idx = S_ORDER.indexOf(memberCode);
  return idx === -1 ? "S?" : `S${idx + 1}`;
}

export function getMemberDisplay(era: string, memberCode: string) {
  const eraMember = ERAS[era]?.members?.[memberCode];
  const sMember = S_MEMBERS[memberCode];
  return {
    name: eraMember?.name ?? sMember?.name ?? memberCode,
    fullName: eraMember?.full_name ?? sMember?.full_name ?? memberCode,
    eraName: ERAS[era]?.name ?? era,
    sNumber: getMemberNumber(memberCode),
    specialty: MEMBER_SPECIALTY[memberCode] ?? "Vocals",
  };
}
