"use client";

import { useState } from "react";
import { Lock, Sparkles, Tag, Zap } from "lucide-react";
import { getRarityMeta } from "@/lib/catalog";
import type { OwnedCard } from "@/lib/db/cards";

interface PhotocardTileProps {
  card: OwnedCard;
  onSelect?: (card: OwnedCard) => void;
}

export function PhotocardTile({ card, onSelect }: PhotocardTileProps) {
  const [imgFailed, setImgFailed] = useState(false);
  const rarity = getRarityMeta(card.rarity);
  const showImage = Boolean(card.imageUrl) && !imgFailed;

  return (
    <button
      type="button"
      onClick={() => onSelect?.(card)}
      className={`group relative flex flex-col overflow-hidden rounded-2xl border bg-[#10101a] text-left transition-all duration-200 hover:-translate-y-1 ${rarity.borderClass} ${rarity.glowClass}`}
    >
      {/* Photocard Image Frame (194:300 ratio matching kotone/images.py) */}
      <div className="relative aspect-[194/300] w-full overflow-hidden bg-[#141422]">
        {showImage ? (
          <img
            src={card.imageUrl!}
            alt={`${card.rarity} ${card.memberName} (${card.eraName})`}
            loading="lazy"
            onError={() => setImgFailed(true)}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-between bg-gradient-to-br from-[#19192a] via-[#12121e] to-[#0b0b14] p-4 text-center">
            <div className="flex w-full items-center justify-between text-[10px] font-semibold uppercase tracking-widest text-zinc-400">
              <span>{card.sNumber}</span>
              <span>{card.eraName}</span>
            </div>
            <div className="my-auto flex flex-col items-center gap-1.5">
              <div
                className="flex h-12 w-12 items-center justify-center rounded-full border border-white/15 bg-white/5 text-sm font-bold"
                style={{ color: rarity.accentHex }}
              >
                {card.memberCode}
              </div>
              <p className="text-sm font-bold text-white">{card.memberName}</p>
              <p className="text-[11px] text-zinc-400">Artwork pending</p>
            </div>
            <div className="h-1 w-12 rounded-full bg-white/10" />
          </div>
        )}

        {/* Holographic sheen overlay for Epic / Legendary / Mythic */}
        {rarity.isHolo && (
          <div className="holo-foil pointer-events-none absolute inset-0 opacity-0 mix-blend-screen transition-opacity duration-300 group-hover:opacity-100" />
        )}

        {/* Top badges */}
        <div className="pointer-events-none absolute inset-x-2 top-2 flex items-start justify-between gap-1">
          <span
            className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-bold tracking-wide backdrop-blur-md ${rarity.badgeClass}`}
          >
            {card.rarity}
          </span>

          <div className="flex items-center gap-1">
            {card.animatedUrl && (
              <span
                title="Animated GIF available"
                className="inline-flex h-5 items-center gap-0.5 rounded-md border border-amber-400/50 bg-black/70 px-1.5 text-[10px] font-bold text-amber-300 backdrop-blur-md"
              >
                <Sparkles className="h-2.5 w-2.5" />
                GIF
              </span>
            )}
            {card.inBinder && (
              <span
                title="Protected in Binder"
                className="inline-flex h-5 w-5 items-center justify-center rounded-md border border-[#ff6b8b]/50 bg-black/75 text-[#ff6b8b] backdrop-blur-md"
              >
                <Lock className="h-3 w-3" />
              </span>
            )}
          </div>
        </div>

        {/* Bottom Market / Copy badge */}
        <div className="pointer-events-none absolute inset-x-2 bottom-2 flex items-center justify-between gap-1">
          {card.marketPrice !== null ? (
            <span className="inline-flex items-center gap-1 rounded-md border border-emerald-400/50 bg-black/80 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300 backdrop-blur-md">
              <Tag className="h-2.5 w-2.5" />
              {card.marketPrice.toLocaleString()} COMO
            </span>
          ) : (
            <span />
          )}

          {card.copyCount > 1 && (
            <span className="rounded-md border border-white/15 bg-black/75 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-zinc-200 backdrop-blur-md">
              ×{card.copyCount}
            </span>
          )}
        </div>
      </div>

      {/* Photocard Footer Metadata */}
      <div className="flex flex-col gap-1.5 p-3">
        <div className="flex items-baseline justify-between gap-2">
          <p className="truncate text-sm font-bold text-white">
            {card.memberName}
          </p>
          <span className="shrink-0 text-[11px] font-medium text-zinc-400">
            {card.eraName}
          </span>
        </div>

        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-[11px] text-zinc-400">
            {card.serial}
          </span>
          {card.skillPoints !== null ? (
            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-zinc-300">
              <Zap className="h-3 w-3 text-[#ff6b8b]" />
              {card.skillPoints}/{card.skillCap}
            </span>
          ) : (
            <span className="text-[11px] text-zinc-500">{card.skill}</span>
          )}
        </div>
      </div>
    </button>
  );
}
