"""Export static Kotone Bot catalog data (eras, members, rarities, shop) to JSON.

Strictly read-only: avoids importing `kotone.db` (which runs `init_db()` on import).
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[1]
BOT_ROOT = WEB_ROOT.parent
OUTPUT_PATH = WEB_ROOT / "src" / "data" / "catalog.json"

sys.path.insert(0, str(BOT_ROOT))

import eras  # noqa: E402
from kotone import config  # noqa: E402


def extract_shop_constants(shop_path: Path) -> dict[str, object]:
    """Read constant literals from kotone/shop.py without importing kotone.db."""
    tree = ast.parse(shop_path.read_text(encoding="utf-8"))
    target_names = {
        "DROP_BOOSTER_DURATION",
        "DROP_BOOSTER_RARITY_MULTIPLIER",
        "SHOP_ITEMS",
    }
    extracted: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in target_names:
                extracted[target.id] = ast.literal_eval(node.value)
    return extracted


def main() -> None:
    shop_constants = extract_shop_constants(BOT_ROOT / "kotone" / "shop.py")

    payload = {
        "eras": eras.ERAS,
        "eraOrder": list(eras.ERAS.keys()),
        "eraAliases": {k: list(v) for k, v in eras.ERA_ALIASES.items()},
        "rarities": config.RARITIES,
        "rarityOrder": list(config.RARITIES.keys()),
        "rarityAbilityRolls": config.RARITY_ABILITY_ROLLS,
        "sOrder": list(config.S_ORDER),
        "sMembers": config.S_MEMBERS,
        "memberSpecialty": config.MEMBER_SPECIALTY,
        "spinDailyLimit": config.SPIN_DAILY_LIMIT,
        "cooldownDurations": {
            "train": config.TRAIN_COOLDOWN_SECONDS,
            "perform": config.PERFORM_COOLDOWN_SECONDS,
            "hunt": config.HUNT_COOLDOWN_SECONDS,
            "daily": 86400,
            "weekly": 604800,
        },
        "shopItems": shop_constants.get("SHOP_ITEMS", {}),
        "dropBoosterDuration": shop_constants.get("DROP_BOOSTER_DURATION", 3600),
        "dropBoosterRarityMultiplier": shop_constants.get(
            "DROP_BOOSTER_RARITY_MULTIPLIER", 1.5
        ),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Synced catalog to {OUTPUT_PATH} "
        f"({len(payload['eraOrder'])} eras, {len(payload['sOrder'])} members)."
    )


if __name__ == "__main__":
    main()
