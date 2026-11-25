import { CodexClient } from "@/components/CodexClient";
import { ERA_ORDER, RARITY_ORDER, S_ORDER } from "@/lib/catalog";

export default function CodexPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-black tracking-tight text-white">
          tripleS Card Codex
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          Browse all {ERA_ORDER.length} eras, {S_ORDER.length} members (S1–S24),
          and {RARITY_ORDER.length} rarity tiers from Kotone Bot&apos;s catalog.
        </p>
      </div>

      <CodexClient />
    </div>
  );
}
