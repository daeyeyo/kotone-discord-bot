"use client";

import { useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import {
  ERAS,
  ERA_ORDER,
  MEMBER_SPECIALTY,
  RARITY_ORDER,
  getAnimatedCardImage,
  getCardImage,
  getMemberNumber,
  getRarityMeta,
} from "@/lib/catalog";

export function CodexClient() {
  const [selectedEra, setSelectedEra] = useState(ERA_ORDER[0] ?? "AAA");
  const [selectedRarity, setSelectedRarity] = useState("Common");
  const [showAnimated, setShowAnimated] = useState(false);
  const [failedImages, setFailedImages] = useState<Record<string, boolean>>({});

  const eraData = ERAS[selectedEra];
  const members = useMemo(
    () => (eraData ? Object.entries(eraData.members) : []),
    [eraData]
  );
  const rarityMeta = getRarityMeta(selectedRarity);

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="flex flex-col justify-between gap-4 rounded-3xl border border-white/10 bg-[#10101a]/90 p-5 lg:flex-row lg:items-center">
        <div className="flex flex-wrap gap-2">
          {ERA_ORDER.map((eraKey) => (
            <button
              key={eraKey}
              type="button"
              onClick={() => setSelectedEra(eraKey)}
              className={`rounded-xl border px-3.5 py-2 text-sm font-semibold transition ${
                selectedEra === eraKey
                  ? "border-[#ff6b8b] bg-[#ff6b8b] text-white shadow-[0_0_20px_-4px_rgba(255,107,139,0.65)]"
                  : "border-white/10 bg-black/40 text-zinc-300 hover:border-white/25 hover:text-white"
              }`}
            >
              {ERAS[eraKey].name} (
              {Object.keys(ERAS[eraKey].members).length})
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {RARITY_ORDER.map((rarityName) => {
            const meta = getRarityMeta(rarityName);
            const active = selectedRarity === rarityName;
            return (
              <button
                key={rarityName}
                type="button"
                onClick={() => setSelectedRarity(rarityName)}
                className={`rounded-xl border px-3 py-1.5 text-xs font-bold transition ${
                  active
                    ? meta.badgeClass
                    : "border-white/10 bg-black/40 text-zinc-400 hover:text-white"
                }`}
              >
                {rarityName}
              </button>
            );
          })}

          {selectedRarity === "Legendary" && (
            <button
              type="button"
              onClick={() => setShowAnimated((v) => !v)}
              className={`inline-flex items-center gap-1 rounded-xl border px-3 py-1.5 text-xs font-semibold transition ${
                showAnimated
                  ? "border-amber-400/60 bg-amber-400/15 text-amber-200"
                  : "border-white/10 bg-black/40 text-zinc-300 hover:text-white"
              }`}
            >
              <Sparkles className="h-3.5 w-3.5" />
              GIF Mode
            </button>
          )}
        </div>
      </div>

      {/* Member Showcase Grid */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {members.map(([memberCode, member]) => {
          const animatedUrl =
            selectedRarity === "Legendary"
              ? getAnimatedCardImage(selectedEra, memberCode, selectedRarity)
              : null;
          const imgUrl =
            showAnimated && animatedUrl
              ? animatedUrl
              : getCardImage(selectedEra, memberCode, selectedRarity);

          return (
            <div
              key={memberCode}
              className={`group overflow-hidden rounded-2xl border bg-[#10101a] transition hover:-translate-y-1 ${rarityMeta.borderClass} ${rarityMeta.glowClass}`}
            >
              <div className="relative aspect-[194/300] w-full overflow-hidden bg-[#141422]">
                {imgUrl && !failedImages[imgUrl] ? (
                  <img
                    src={imgUrl}
                    alt={`${selectedRarity} ${member.name}`}
                    loading="lazy"
                    onError={() =>
                      setFailedImages((prev) => ({ ...prev, [imgUrl]: true }))
                    }
                    className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.03]"
                  />
                ) : (
                  <div className="flex h-full w-full flex-col items-center justify-center p-4 text-center">
                    <span className="text-sm font-bold text-white">
                      {member.name}
                    </span>
                    <span className="text-xs text-zinc-500">
                      Artwork pending
                    </span>
                  </div>
                )}

                <span
                  className={`absolute left-2 top-2 rounded-md border px-1.5 py-0.5 text-[10px] font-bold backdrop-blur-md ${rarityMeta.badgeClass}`}
                >
                  {selectedRarity}
                </span>

                {animatedUrl && (
                  <span className="absolute right-2 top-2 inline-flex items-center gap-0.5 rounded-md border border-amber-400/50 bg-black/75 px-1.5 py-0.5 text-[10px] font-bold text-amber-300">
                    <Sparkles className="h-2.5 w-2.5" />
                    GIF
                  </span>
                )}
              </div>

              <div className="space-y-0.5 p-3">
                <div className="flex items-center justify-between gap-1">
                  <p className="truncate text-sm font-bold text-white">
                    {member.name}
                  </p>
                  <span className="font-mono text-[10px] text-zinc-400">
                    {getMemberNumber(memberCode)}
                  </span>
                </div>
                <p className="truncate text-[11px] text-zinc-400">
                  {member.full_name}
                </p>
                <p className="text-[10px] font-medium text-[#ff9bb0]">
                  Specialty: {MEMBER_SPECIALTY[memberCode] ?? "Vocals"}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
