"use client";

import { useMemo, useState } from "react";
import {
  CheckCircle2,
  Filter,
  Grid2x2,
  Layers,
  Lock,
  Search,
  Tag,
} from "lucide-react";
import {
  ERAS,
  ERA_ORDER,
  RARITY_ORDER,
  S_MEMBERS,
  S_ORDER,
  getCardImage,
  getRarityMeta,
} from "@/lib/catalog";
import type { EraCompletionSummary, OwnedCard } from "@/lib/db/cards";
import { CardDetailModal } from "./CardDetailModal";
import { PhotocardTile } from "./PhotocardTile";

interface PlayerCollectionViewProps {
  cards: OwnedCard[];
  eraCompletion: EraCompletionSummary[];
}

type ActiveTab = "binder" | "completion";
type SortBy = "newest" | "rarity" | "skill" | "member" | "serial";

export function PlayerCollectionView({
  cards,
  eraCompletion,
}: PlayerCollectionViewProps) {
  const [activeTab, setActiveTab] = useState<ActiveTab>("binder");
  const [selectedCard, setSelectedCard] = useState<OwnedCard | null>(null);

  // Binder filters
  const [search, setSearch] = useState("");
  const [eraFilter, setEraFilter] = useState("ALL");
  const [memberFilter, setMemberFilter] = useState("ALL");
  const [rarityFilter, setRarityFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState<
    "all" | "binder" | "listed" | "dupes"
  >("all");
  const [sortBy, setSortBy] = useState<SortBy>("rarity");

  // Era completion controls
  const [selectedEra, setSelectedEra] = useState(
    eraCompletion[0]?.era ?? "ASSEMBLE24"
  );
  const [selectedCompletionRarity, setSelectedCompletionRarity] =
    useState("Common");
  const [failedCompletionImages, setFailedCompletionImages] = useState<
    Record<string, boolean>
  >({});

  const filteredCards = useMemo(() => {
    const query = search.trim().toLowerCase();

    const list = cards.filter((card) => {
      if (eraFilter !== "ALL" && card.era !== eraFilter) return false;
      if (memberFilter !== "ALL" && card.memberCode !== memberFilter)
        return false;
      if (rarityFilter !== "ALL" && card.rarity !== rarityFilter) return false;
      if (statusFilter === "binder" && !card.inBinder) return false;
      if (statusFilter === "listed" && card.marketPrice === null) return false;
      if (statusFilter === "dupes" && card.copyCount <= 1) return false;

      if (query) {
        const haystack =
          `${card.serial} ${card.memberName} ${card.memberFullName} ${card.memberCode} ${card.eraName} ${card.rarity}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });

    return [...list].sort((a, b) => {
      if (sortBy === "newest") return b.id - a.id;
      if (sortBy === "rarity") {
        return (
          b.rarityRank - a.rarityRank ||
          (b.skillPoints ?? 0) - (a.skillPoints ?? 0) ||
          b.id - a.id
        );
      }
      if (sortBy === "skill") {
        return (
          (b.skillPoints ?? -1) - (a.skillPoints ?? -1) ||
          b.rarityRank - a.rarityRank
        );
      }
      if (sortBy === "member") {
        return (
          S_ORDER.indexOf(a.memberCode) - S_ORDER.indexOf(b.memberCode) ||
          b.rarityRank - a.rarityRank
        );
      }
      return a.serial.localeCompare(b.serial);
    });
  }, [
    cards,
    search,
    eraFilter,
    memberFilter,
    rarityFilter,
    statusFilter,
    sortBy,
  ]);

  const currentEraSummary = useMemo(
    () =>
      eraCompletion.find((item) => item.era === selectedEra) ?? eraCompletion[0],
    [eraCompletion, selectedEra]
  );

  const eraMembers = useMemo(() => {
    if (!currentEraSummary) return [];
    const eraObj = ERAS[currentEraSummary.era];
    if (!eraObj) return [];
    return Object.entries(eraObj.members);
  }, [currentEraSummary]);

  return (
    <div className="space-y-6">
      {/* Sub-navigation Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-2xl border border-white/10 bg-[#10101a] p-1">
          <button
            type="button"
            onClick={() => setActiveTab("binder")}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition ${
              activeTab === "binder"
                ? "bg-[#ff6b8b] text-white shadow-[0_0_20px_-4px_rgba(255,107,139,0.7)]"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            <Grid2x2 className="h-4 w-4" />
            Photocard Binder ({cards.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("completion")}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition ${
              activeTab === "completion"
                ? "bg-[#ff6b8b] text-white shadow-[0_0_20px_-4px_rgba(255,107,139,0.7)]"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            <Layers className="h-4 w-4" />
            Era Completion
          </button>
        </div>

        {activeTab === "binder" && (
          <p className="text-xs text-zinc-400">
            Showing <strong className="text-white">{filteredCards.length}</strong>{" "}
            of {cards.length} cards
          </p>
        )}
      </div>

      {activeTab === "binder" ? (
        <>
          {/* Filter Bar */}
          <div className="rounded-2xl border border-white/10 bg-[#10101a]/90 p-4">
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-6">
              <div className="relative lg:col-span-2">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search serial, member, or era..."
                  className="h-10 w-full rounded-xl border border-white/10 bg-black/40 pl-9 pr-3 text-sm text-white placeholder:text-zinc-500 focus:border-[#ff6b8b]/60 focus:outline-none"
                />
              </div>

              <select
                value={eraFilter}
                onChange={(e) => setEraFilter(e.target.value)}
                className="h-10 rounded-xl border border-white/10 bg-black/40 px-3 text-sm text-zinc-200 focus:border-[#ff6b8b]/60 focus:outline-none"
              >
                <option value="ALL">All Eras</option>
                {ERA_ORDER.map((era) => (
                  <option key={era} value={era}>
                    {ERAS[era].name}
                  </option>
                ))}
              </select>

              <select
                value={memberFilter}
                onChange={(e) => setMemberFilter(e.target.value)}
                className="h-10 rounded-xl border border-white/10 bg-black/40 px-3 text-sm text-zinc-200 focus:border-[#ff6b8b]/60 focus:outline-none"
              >
                <option value="ALL">All 24 Members</option>
                {S_ORDER.map((code, idx) => (
                  <option key={code} value={code}>
                    S{idx + 1} • {S_MEMBERS[code]?.name ?? code}
                  </option>
                ))}
              </select>

              <select
                value={rarityFilter}
                onChange={(e) => setRarityFilter(e.target.value)}
                className="h-10 rounded-xl border border-white/10 bg-black/40 px-3 text-sm text-zinc-200 focus:border-[#ff6b8b]/60 focus:outline-none"
              >
                <option value="ALL">All Rarities</option>
                {RARITY_ORDER.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>

              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortBy)}
                className="h-10 rounded-xl border border-white/10 bg-black/40 px-3 text-sm text-zinc-200 focus:border-[#ff6b8b]/60 focus:outline-none"
              >
                <option value="rarity">Sort: Rarity</option>
                <option value="newest">Sort: Newest</option>
                <option value="skill">Sort: Skill Points</option>
                <option value="member">Sort: S1–S24 Order</option>
                <option value="serial">Sort: Serial</option>
              </select>
            </div>

            {/* Quick Status Chips */}
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/5 pt-3">
              <span className="inline-flex items-center gap-1 text-xs text-zinc-400">
                <Filter className="h-3.5 w-3.5" />
                Quick Filter:
              </span>
              {(
                [
                  ["all", "All Cards"],
                  ["binder", "In Binder"],
                  ["listed", "On Market"],
                  ["dupes", "Duplicates"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setStatusFilter(key)}
                  className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                    statusFilter === key
                      ? "border-[#ff6b8b]/60 bg-[#ff6b8b]/15 text-[#ff9bb0]"
                      : "border-white/10 bg-white/5 text-zinc-400 hover:text-white"
                  }`}
                >
                  {key === "binder" && <Lock className="h-3 w-3" />}
                  {key === "listed" && <Tag className="h-3 w-3" />}
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Photocard Grid */}
          {filteredCards.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-white/15 bg-[#10101a]/60 px-6 py-16 text-center">
              <p className="text-base font-semibold text-white">
                No photocards match these filters
              </p>
              <p className="mt-1 text-sm text-zinc-400">
                Try clearing your search or switching era/rarity filters.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
              {filteredCards.map((card) => (
                <PhotocardTile
                  key={card.serial}
                  card={card}
                  onSelect={setSelectedCard}
                />
              ))}
            </div>
          )}
        </>
      ) : (
        /* Era Completion Matrix */
        <div className="space-y-6">
          {/* Era Progress Cards */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {eraCompletion.map((eraItem) => {
              const isSelected = eraItem.era === currentEraSummary?.era;
              return (
                <button
                  key={eraItem.era}
                  type="button"
                  onClick={() => setSelectedEra(eraItem.era)}
                  className={`rounded-2xl border p-4 text-left transition ${
                    isSelected
                      ? "border-[#ff6b8b] bg-[#ff6b8b]/10 shadow-[0_0_24px_-8px_rgba(255,107,139,0.65)]"
                      : "border-white/10 bg-[#10101a]/80 hover:border-white/25"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-white">
                      {eraItem.eraName}
                    </span>
                    <span className="font-mono text-xs font-bold text-[#ff9bb0]">
                      {eraItem.percentage}%
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-zinc-400">
                    {eraItem.ownedSlots}/{eraItem.totalSlots} slots •{" "}
                    {eraItem.totalCopies} total
                  </p>
                  <div className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-[#ff6b8b] to-violet-400"
                      style={{ width: `${eraItem.percentage}%` }}
                    />
                  </div>
                </button>
              );
            })}
          </div>

          {currentEraSummary && (
            <div className="rounded-3xl border border-white/10 bg-[#10101a]/90 p-5 sm:p-6">
              {/* Rarity Tabs */}
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-4">
                <div>
                  <h2 className="text-lg font-bold text-white">
                    {currentEraSummary.eraName} • {selectedCompletionRarity}{" "}
                    Slots
                  </h2>
                  <p className="text-xs text-zinc-400">
                    Owned photocards appear in full color; missing slots are
                    dimmed just like /collection.
                  </p>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {RARITY_ORDER.map((rarityName) => {
                    const progress = currentEraSummary.byRarity[rarityName];
                    const rarityMeta = getRarityMeta(rarityName);
                    const active = selectedCompletionRarity === rarityName;
                    return (
                      <button
                        key={rarityName}
                        type="button"
                        onClick={() => setSelectedCompletionRarity(rarityName)}
                        className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition ${
                          active
                            ? rarityMeta.badgeClass
                            : "border-white/10 bg-white/5 text-zinc-400 hover:text-white"
                        }`}
                      >
                        <span>{rarityName}</span>
                        <span className="font-mono">
                          {progress?.ownedCount ?? 0}/
                          {progress?.totalMembers ?? 0}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Member Slots Grid */}
              <div className="mt-5 grid grid-cols-2 gap-3.5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
                {eraMembers.map(([memberCode, memberData]) => {
                  const rarityProgress =
                    currentEraSummary.byRarity[selectedCompletionRarity];
                  const copies =
                    rarityProgress?.copyCountsByMember[memberCode] ?? 0;
                  const owned = copies > 0;
                  const imgUrl = getCardImage(
                    currentEraSummary.era,
                    memberCode,
                    selectedCompletionRarity
                  );
                  const rarityMeta = getRarityMeta(selectedCompletionRarity);

                  return (
                    <div
                      key={memberCode}
                      className={`relative overflow-hidden rounded-2xl border bg-[#0b0b14] transition ${
                        owned
                          ? `${rarityMeta.borderClass} ${rarityMeta.glowClass}`
                          : "border-white/10 opacity-55"
                      }`}
                    >
                      <div className="relative aspect-[194/300] w-full overflow-hidden bg-[#141422]">
                        {imgUrl && !failedCompletionImages[imgUrl] ? (
                          <img
                            src={imgUrl}
                            alt={`${selectedCompletionRarity} ${memberData.name}`}
                            loading="lazy"
                            onError={() =>
                              setFailedCompletionImages((prev) => ({
                                ...prev,
                                [imgUrl]: true,
                              }))
                            }
                            className={`h-full w-full object-cover transition ${
                              owned ? "" : "brightness-50 grayscale"
                            }`}
                          />
                        ) : (
                          <div className="flex h-full w-full flex-col items-center justify-center p-3 text-center">
                            <span className="text-sm font-bold text-zinc-200">
                              {memberData.name}
                            </span>
                            <span className="text-[11px] text-zinc-500">
                              {memberCode}
                            </span>
                          </div>
                        )}

                        <div className="absolute right-2 top-2">
                          {owned ? (
                            <span className="inline-flex items-center gap-1 rounded-md border border-emerald-400/50 bg-black/80 px-1.5 py-0.5 font-mono text-[10px] font-bold text-emerald-300">
                              <CheckCircle2 className="h-3 w-3" />×{copies}
                            </span>
                          ) : (
                            <span className="rounded-md border border-white/15 bg-black/80 px-1.5 py-0.5 text-[10px] font-semibold text-zinc-400">
                              Missing
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center justify-between px-3 py-2">
                        <span className="truncate text-xs font-bold text-white">
                          {memberData.name}
                        </span>
                        <span className="font-mono text-[10px] text-zinc-400">
                          {memberCode}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      <CardDetailModal
        card={selectedCard}
        onClose={() => setSelectedCard(null)}
      />
    </div>
  );
}
