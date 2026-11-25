"use client";

import { useEffect, useState } from "react";
import {
  Calendar,
  Check,
  Copy,
  Lock,
  Sparkles,
  Tag,
  X,
  Zap,
} from "lucide-react";
import { getRarityMeta } from "@/lib/catalog";
import type { OwnedCard } from "@/lib/db/cards";

interface CardDetailModalProps {
  card: OwnedCard | null;
  onClose: () => void;
}

export function CardDetailModal({ card, onClose }: CardDetailModalProps) {
  const [showAnimated, setShowAnimated] = useState(false);
  const [copied, setCopied] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);

  useEffect(() => {
    setShowAnimated(Boolean(card?.animatedUrl));
    setCopied(false);
    setImgFailed(false);
  }, [card?.serial, card?.animatedUrl]);

  useEffect(() => {
    if (!card) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [card, onClose]);

  if (!card) return null;

  const rarity = getRarityMeta(card.rarity);
  const activeUrl =
    showAnimated && card.animatedUrl ? card.animatedUrl : card.imageUrl;
  const skillPoints = card.skillPoints ?? 0;
  const skillPct = Math.min(
    100,
    Math.round((skillPoints / Math.max(1, card.skillCap)) * 100)
  );

  const handleCopySerial = async () => {
    try {
      await navigator.clipboard.writeText(card.serial);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard may be unavailable in non-HTTPS contexts
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md"
      onClick={onClose}
    >
      <div
        className={`relative grid w-full max-w-3xl overflow-hidden rounded-3xl border bg-[#0e0e18] shadow-2xl md:grid-cols-[300px_1fr] ${rarity.borderClass}`}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close modal"
          className="absolute right-4 top-4 z-10 flex h-8 w-8 items-center justify-center rounded-full border border-white/15 bg-black/60 text-zinc-300 transition hover:bg-white/10 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Left: Photocard Artwork */}
        <div className="relative flex flex-col items-center justify-center bg-[#090910] p-6">
          <div
            className={`relative aspect-[194/300] w-56 overflow-hidden rounded-2xl border bg-[#141422] ${rarity.borderClass} ${rarity.glowClass}`}
          >
            {activeUrl && !imgFailed ? (
              <img
                src={activeUrl}
                alt={`${card.rarity} ${card.memberName}`}
                onError={() => setImgFailed(true)}
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-6 text-center">
                <span className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
                  {card.sNumber} • {card.eraName}
                </span>
                <span className="text-xl font-bold text-white">
                  {card.memberName}
                </span>
                <span className="text-xs text-zinc-500">
                  Card image unavailable
                </span>
              </div>
            )}
          </div>

          {card.animatedUrl && (
            <button
              type="button"
              onClick={() => {
                setImgFailed(false);
                setShowAnimated((prev) => !prev);
              }}
              className={`mt-4 inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition ${
                showAnimated
                  ? "border-amber-400/60 bg-amber-400/15 text-amber-200"
                  : "border-white/15 bg-white/5 text-zinc-300 hover:bg-white/10"
              }`}
            >
              <Sparkles className="h-3.5 w-3.5" />
              {showAnimated ? "Showing Animated GIF" : "Switch to Animated GIF"}
            </button>
          )}
        </div>

        {/* Right: Metadata & Training Progress */}
        <div className="flex flex-col justify-between gap-6 p-6 sm:p-7">
          <div className="space-y-5">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-bold ${rarity.badgeClass}`}
                >
                  {card.rarity}
                </span>
                <span className="rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-xs font-medium text-zinc-300">
                  {card.eraName}
                </span>
                <span className="rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-xs font-medium text-zinc-300">
                  {card.sNumber}
                </span>
              </div>

              <h2 className="mt-3 text-2xl font-extrabold tracking-tight text-white">
                {card.memberFullName}
              </h2>
              <p className="text-sm text-zinc-400">
                Stage Name: <span className="text-zinc-200">{card.memberName}</span>
              </p>
            </div>

            {/* Serial & Status Badges */}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleCopySerial}
                className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 font-mono text-xs font-semibold text-zinc-200 transition hover:border-[#ff6b8b]/50 hover:bg-white/10"
              >
                <span>{card.serial}</span>
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-emerald-400" />
                ) : (
                  <Copy className="h-3.5 w-3.5 text-zinc-400" />
                )}
              </button>

              {card.inBinder && (
                <span className="inline-flex items-center gap-1.5 rounded-xl border border-[#ff6b8b]/40 bg-[#ff6b8b]/10 px-3 py-1.5 text-xs font-semibold text-[#ff9bb0]">
                  <Lock className="h-3.5 w-3.5" />
                  Protected in Binder
                </span>
              )}

              {card.marketPrice !== null && (
                <span className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-400/40 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-300">
                  <Tag className="h-3.5 w-3.5" />
                  Listed for {card.marketPrice.toLocaleString()} COMO
                </span>
              )}
            </div>

            {/* Skill & Training Panel */}
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-1.5 font-semibold text-white">
                  <Zap className="h-4 w-4 text-[#ff6b8b]" />
                  {card.skill} Specialty
                </span>
                <span className="font-mono text-xs text-zinc-300">
                  {card.skillPoints !== null
                    ? `${card.skillPoints} / ${card.skillCap} pts`
                    : `Unrolled (Cap ${card.skillCap})`}
                </span>
              </div>

              <div className="mt-2.5 h-2 w-full overflow-hidden rounded-full bg-white/10">
                <div
                  className={`h-full rounded-full transition-all ${rarity.barClass}`}
                  style={{
                    width: `${card.skillPoints !== null ? skillPct : 0}%`,
                  }}
                />
              </div>

              <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-zinc-400">
                <div className="rounded-xl bg-black/30 px-3 py-2">
                  <p className="text-[11px] text-zinc-500">Training Sessions</p>
                  <p className="mt-0.5 font-semibold text-zinc-200">
                    {card.trainingSessions}
                  </p>
                </div>
                <div className="rounded-xl bg-black/30 px-3 py-2">
                  <p className="text-[11px] text-zinc-500">Performances</p>
                  <p className="mt-0.5 font-semibold text-zinc-200">
                    {card.performances}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-4 text-xs text-zinc-400">
            <span className="inline-flex items-center gap-1.5">
              <Calendar className="h-3.5 w-3.5" />
              Obtained:{" "}
              {card.obtainedAt ? card.obtainedAt.slice(0, 16) : "Unknown"}
            </span>
            <span>
              Copies owned:{" "}
              <strong className="text-zinc-200">{card.copyCount}</strong>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
