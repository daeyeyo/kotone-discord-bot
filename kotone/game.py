import datetime
import random
import time
from eras import ERAS
from kotone.config import (
    HUNT_COMO_REWARDS,
    HUNT_COOLDOWN_SECONDS,
    MEMBER_SPECIALTY,
    PERFORM_BASE_SCORE,
    PERFORM_COOLDOWN_SECONDS,
    PERFORM_GRADE_MULTIPLIERS,
    PERFORM_RARITY_MULTIPLIERS,
    PERFORM_SKILL_WEIGHT,
    RARITIES,
    RARITY_ABILITY_ROLLS,
    SPIN_BOARD_SIZE,
    SPIN_BOMB_SLOTS,
    SPIN_DAILY_LIMIT,
    SPIN_REWARD_COUNTS,
    S_MEMBERS,
    S_ORDER,
    TRAIN_COOLDOWN_SECONDS,
    TRAIN_GAIN_MAX,
    TRAIN_GAIN_MIN,
    TRAIN_PERFECT_BONUS,
    TRAIN_PERFECT_CHANCE,
)
from kotone.cooldowns import (
    next_local_midnight_timestamp,
    schedule_cooldown_reminder,
)
from kotone.db import (
    get_db,
)
from kotone.shop import (
    DROP_BOOSTER_RARITY_MULTIPLIER,
)


# Generate a random card with guaranteed uniqueness
def get_user_target(user_id):
    """Return the user's target preference, if one is set."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT era, member_code, rarity FROM user_targets WHERE user_id=?",
            (user_id,),
        )
        result = c.fetchone()
    if result:
        return {"era": result[0], "member_code": result[1], "rarity": result[2]}
    return None

def generate_card(
    max_attempts=100,
    target=None,
    forced_rarity=None,
    connection=None,
    rarity_boost=False,
):
    """Generate a unique card, optionally targeted or restricted to one rarity."""
    for attempt in range(max_attempts):
        candidates = []
        for rarity, rarity_weight in RARITIES.items():
            if forced_rarity and rarity != forced_rarity:
                continue
            for era, era_data in ERAS.items():
                member_weight = 1 / len(ERAS) / len(era_data["members"])
                for member_code in era_data["members"]:
                    candidates.append((
                        rarity,
                        era,
                        member_code,
                        rarity_weight / sum(RARITIES.values()) * member_weight,
                    ))

        weights = [candidate[3] for candidate in candidates]
        if rarity_boost:
            weights = [
                weight * (
                    DROP_BOOSTER_RARITY_MULTIPLIER
                    if candidate[0] != "Common"
                    else 1
                )
                for candidate, weight in zip(candidates, weights)
            ]
            total_weight = sum(weights)
            weights = [weight / total_weight for weight in weights]
        if target:
            target_indices = [
                index for index, (rarity, era, member_code, _) in enumerate(candidates)
                if member_code == target["member_code"]
                and (target["era"] is None or era == target["era"])
                and (target["rarity"] is None or rarity == target["rarity"])
            ]
            if target_indices:
                target_probability = sum(weights[index] for index in target_indices)
                if target.get("rarity") == "Mythic":
                    # A Mythic target must not increase the overall Mythic drop rate.
                    other_indices = [
                        index for index, candidate in enumerate(candidates)
                        if candidate[0] == "Mythic" and index not in target_indices
                    ]
                    other_probability = sum(weights[index] for index in other_indices)
                    rarity_probability = target_probability + other_probability
                    boosted_probability = min(
                        target_probability + rarity_probability * 0.01,
                        rarity_probability,
                    )
                    remaining_probability = rarity_probability - boosted_probability
                else:
                    boosted_probability = min(target_probability + 0.01, 1.0)
                    other_indices = [
                        index for index in range(len(weights))
                        if index not in target_indices
                    ]
                    other_probability = 1 - target_probability
                    remaining_probability = 1 - boosted_probability
                target_scale = boosted_probability / target_probability
                other_scale = (
                    remaining_probability / other_probability
                    if other_probability else 0
                )
                for index in target_indices:
                    weights[index] *= target_scale
                for index in other_indices:
                    weights[index] *= other_scale

        rarity, era, member_code = random.choices(
            [
                (candidate[0], candidate[1], candidate[2])
                for candidate in candidates
            ],
            weights=weights,
            k=1,
        )[0]
        
        # Generate serial
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        random_part = ''.join(random.choices(chars, k=5))
        serial = f"{member_code}-{random_part}"
        
        # Check if serial already exists
        if connection is None:
            with get_db() as conn:
                c = conn.cursor()
                c.execute("SELECT serial FROM cards WHERE serial=?", (serial,))
                serial_exists = c.fetchone()
        else:
            c = connection.cursor()
            c.execute("SELECT serial FROM cards WHERE serial=?", (serial,))
            serial_exists = c.fetchone()

        if not serial_exists:
            # Serial is unique
            return {
                "serial": serial,
                "member_code": member_code,
                "era": era,
                "name": ERAS[era]["members"][member_code]["name"],
                "full_name": ERAS[era]["members"][member_code]["full_name"],
                "rarity": rarity
            }
    
    # If we somehow can't generate unique serial after max_attempts
    raise RuntimeError("Failed to generate unique card serial")

# Generate multiple unique cards
def generate_unique_cards(count=3, target=None, rarity_boost=False):
    """Generate unique cards, optionally applying a small target bonus."""
    cards = []
    generated_serials = set()
    
    for _ in range(count):
        max_attempts = 100
        for attempt in range(max_attempts):
            card = generate_card(target=target, rarity_boost=rarity_boost)
            if card['serial'] not in generated_serials:
                cards.append(card)
                generated_serials.add(card['serial'])
                break
            
            if attempt == max_attempts - 1:
                raise Exception("Failed to generate unique cards")
    
    return cards


def format_duration(seconds):
    seconds = max(0, int(seconds))
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def _roll_skill(member_code, rarity):
    skill = MEMBER_SPECIALTY.get(member_code, "Vocals")
    rolls = RARITY_ABILITY_ROLLS.get(
        rarity,
        RARITY_ABILITY_ROLLS["Common"],
    )
    skill_min, skill_max = rolls["specialty"]
    return skill, random.randint(skill_min, skill_max)


def ensure_card_skill(cursor, serial, member_code, rarity):
    cursor.execute(
        '''SELECT skill, points, training_sessions, performances,
                  last_trained
           FROM card_skill_points WHERE card_serial=?''',
        (serial,),
    )
    row = cursor.fetchone()
    if row is None:
        skill, points = _roll_skill(member_code, rarity)
        cursor.execute(
            '''INSERT OR IGNORE INTO card_skill_points
               (card_serial, skill, points)
               VALUES (?, ?, ?)''',
            (serial, skill, points),
        )
        cursor.execute(
            '''SELECT skill, points, training_sessions, performances,
                      last_trained
               FROM card_skill_points WHERE card_serial=?''',
            (serial,),
        )
        row = cursor.fetchone()

    skill, points, training_sessions, performances, last_trained = row
    rolls = RARITY_ABILITY_ROLLS.get(
        rarity,
        RARITY_ABILITY_ROLLS["Common"],
    )
    return {
        "card_serial": serial,
        "skill": skill,
        "points": points,
        "cap": rolls["cap"],
        "training_sessions": training_sessions,
        "performances": performances,
        "last_trained": last_trained,
    }


def _get_active_cooldown(cursor, user_id, cooldown_type):
    cursor.execute(
        '''SELECT expires_at FROM cooldowns
           WHERE user_id=? AND cooldown_type=?''',
        (user_id, cooldown_type),
    )
    row = cursor.fetchone()
    if row is None:
        return 0
    return max(0, int(row[0] - time.time()))


def _set_user_cooldown(cursor, user_id, cooldown_type, duration):
    expires_at = time.time() + duration
    cursor.execute(
        '''INSERT OR REPLACE INTO cooldowns
           (user_id, cooldown_type, expires_at)
           VALUES (?, ?, ?)''',
        (user_id, cooldown_type, expires_at),
    )
    schedule_cooldown_reminder(
        cursor,
        user_id,
        cooldown_type,
        expires_at,
    )
    return expires_at


VALID_CARD_PREFERENCE_ACTIONS = ("train", "perform", "hunt")


def save_preferred_card(user_id, action, serial):
    """Save a player's default card serial for train, perform, or hunt."""
    if action not in VALID_CARD_PREFERENCE_ACTIONS:
        raise ValueError(f"Unsupported card preference action: {action}")
    cleaned_serial = serial.strip() if serial is not None else ""
    if not cleaned_serial:
        raise ValueError("Enter the card serial to save.")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM cards WHERE serial=? AND owner_id=?",
            (cleaned_serial, user_id),
        )
        if cursor.fetchone() is None:
            raise ValueError("You don't own a card with that serial.")
        cursor.execute(
            '''INSERT OR REPLACE INTO user_card_preferences
               (user_id, action, card_serial)
               VALUES (?, ?, ?)''',
            (user_id, action, cleaned_serial),
        )
    return cleaned_serial


def get_preferred_card(user_id, action):
    """Return the player's saved default card serial if they still own it."""
    if action not in VALID_CARD_PREFERENCE_ACTIONS:
        raise ValueError(f"Unsupported card preference action: {action}")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT p.card_serial, c.serial
               FROM user_card_preferences p
               LEFT JOIN cards c
                 ON c.serial = p.card_serial AND c.owner_id = p.user_id
               WHERE p.user_id = ? AND p.action = ?''',
            (user_id, action),
        )
        row = cursor.fetchone()
    if row is None:
        raise ValueError(
            f"No default card is set for {action}. "
            f"Use `/{action} set:SERIAL` first."
        )
    if row[1] is None:
        raise ValueError(
            f"Your saved {action} card is no longer in your collection. "
            f"Choose a new one with `/{action} set:SERIAL`."
        )
    return row[0]


def _get_card_for_ability(cursor, user_id, serial, action):
    cursor.execute(
        '''SELECT member_code, era, rarity FROM cards
           WHERE serial=? AND owner_id=?''',
        (serial, user_id),
    )
    card = cursor.fetchone()
    if card is None:
        raise ValueError("You don't own a card with that serial.")
    cursor.execute(
        "SELECT 1 FROM market_listings WHERE card_serial=?",
        (serial,),
    )
    if cursor.fetchone():
        raise ValueError(
            f"Unlist that card from the market before {action}."
        )
    return card


def train_card(user_id, serial):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        remaining = _get_active_cooldown(cursor, user_id, "train")
        if remaining > 0:
            raise ValueError(
                "Your training cooldown is still active for "
                f"**{format_duration(remaining)}**."
            )

        member_code, era, rarity = _get_card_for_ability(
            cursor,
            user_id,
            serial,
            "training it",
        )
        member = ERAS[era]["members"][member_code]
        era_name = ERAS[era]["name"]
        skills = ensure_card_skill(cursor, serial, member_code, rarity)
        skill = skills["skill"]
        old_points = skills["points"]
        cap = skills["cap"]
        if old_points >= cap:
            raise ValueError(
                f"{skill} is already at the {rarity} cap of **{cap}**."
            )

        gain = random.randint(TRAIN_GAIN_MIN, TRAIN_GAIN_MAX)
        perfect = random.random() < TRAIN_PERFECT_CHANCE
        if perfect:
            gain += TRAIN_PERFECT_BONUS
        new_points = min(cap, old_points + gain)
        actual_gain = new_points - old_points
        training_sessions = skills["training_sessions"] + 1

        cursor.execute(
            '''UPDATE card_skill_points
               SET points=?,
                   training_sessions=?,
                   last_trained=?
               WHERE card_serial=?''',
            (new_points, training_sessions, time.time(), serial),
        )
        expires_at = _set_user_cooldown(
            cursor,
            user_id,
            "train",
            TRAIN_COOLDOWN_SECONDS,
        )

    return {
        "serial": serial,
        "member_code": member_code,
        "name": member["name"],
        "full_name": member["full_name"],
        "era": era,
        "era_name": era_name,
        "rarity": rarity,
        "skill": skill,
        "old_points": old_points,
        "new_points": new_points,
        "gain": actual_gain,
        "cap": cap,
        "perfect": perfect,
        "training_sessions": training_sessions,
        "points": new_points,
        "cap_reached": new_points >= cap,
        "cooldown_until": expires_at,
    }


def perform_card(user_id, username, serial):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        remaining = _get_active_cooldown(cursor, user_id, "perform")
        if remaining > 0:
            raise ValueError(
                "Your performance cooldown is still active for "
                f"**{format_duration(remaining)}**."
            )

        member_code, era, rarity = _get_card_for_ability(
            cursor,
            user_id,
            serial,
            "performing with it",
        )
        member = ERAS[era]["members"][member_code]
        era_name = ERAS[era]["name"]
        skills = ensure_card_skill(cursor, serial, member_code, rarity)
        skill = skills["skill"]
        points = skills["points"]
        cap = skills["cap"]

        progress = points / cap
        if progress >= 0.9:
            grade = "S"
        elif progress >= 0.7:
            grade = "A"
        elif progress >= 0.45:
            grade = "B"
        else:
            grade = "C"

        score = PERFORM_BASE_SCORE + points * PERFORM_SKILL_WEIGHT
        payout = round(
            score
            * PERFORM_RARITY_MULTIPLIERS.get(rarity, 1.0)
            * PERFORM_GRADE_MULTIPLIERS[grade]
            * random.uniform(0.9, 1.1)
        )
        payout = max(1, payout)
        performances = skills["performances"] + 1

        cursor.execute(
            '''UPDATE card_skill_points
               SET performances=?
               WHERE card_serial=?''',
            (performances, serial),
        )
        cursor.execute(
            "SELECT como FROM users WHERE user_id=?",
            (user_id,),
        )
        user = cursor.fetchone()
        if user is None:
            cursor.execute(
                '''INSERT INTO users (user_id, username, como)
                   VALUES (?, ?, ?)''',
                (user_id, username, payout),
            )
            new_balance = payout
        else:
            cursor.execute(
                '''UPDATE users SET username=?, como=COALESCE(como, 0)+?
                   WHERE user_id=?''',
                (username, payout, user_id),
            )
            new_balance = (user[0] or 0) + payout

        expires_at = _set_user_cooldown(
            cursor,
            user_id,
            "perform",
            PERFORM_COOLDOWN_SECONDS,
        )

    return {
        "serial": serial,
        "member_code": member_code,
        "name": member["name"],
        "full_name": member["full_name"],
        "era": era,
        "era_name": era_name,
        "rarity": rarity,
        "skill": skill,
        "points": points,
        "cap": cap,
        "grade": grade,
        "payout": payout,
        "new_balance": new_balance,
        "performances": performances,
        "cooldown_until": expires_at,
    }


def hunt_card(user_id, username, serial):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        remaining = _get_active_cooldown(cursor, user_id, "hunt")
        if remaining > 0:
            raise ValueError(
                "Your hunt cooldown is still active for "
                f"**{format_duration(remaining)}**."
            )

        member_code, era, rarity = _get_card_for_ability(
            cursor,
            user_id,
            serial,
            "sending it on a hunt",
        )
        skills = ensure_card_skill(cursor, serial, member_code, rarity)
        progress = (
            skills["points"] / skills["cap"]
            if skills["training_sessions"]
            else 0.0
        )
        rarity_weights = [
            weight * (1 + progress if tier != "Common" else 1)
            for tier, weight in RARITIES.items()
        ]
        reward_rarity = random.choices(
            list(RARITIES),
            weights=rarity_weights,
            k=1,
        )[0]
        reward_card = generate_card(
            forced_rarity=reward_rarity,
            connection=conn,
        )

        base_reward = random.randint(*HUNT_COMO_REWARDS[reward_rarity])
        payout = round(base_reward * (1 + progress * 0.5))
        cursor.execute(
            "SELECT como FROM users WHERE user_id=?",
            (user_id,),
        )
        user = cursor.fetchone()
        if user is None:
            cursor.execute(
                '''INSERT INTO users (user_id, username, como)
                   VALUES (?, ?, ?)''',
                (user_id, username, payout),
            )
            new_balance = payout
        else:
            cursor.execute(
                '''UPDATE users SET username=?, como=COALESCE(como, 0)+?
                   WHERE user_id=?''',
                (username, payout, user_id),
            )
            new_balance = (user[0] or 0) + payout

        cursor.execute(
            '''INSERT INTO cards
               (serial, member_code, era, rarity, owner_id, obtained_at)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (
                reward_card["serial"],
                reward_card["member_code"],
                reward_card["era"],
                reward_card["rarity"],
                user_id,
                datetime.datetime.now().isoformat(),
            ),
        )
        expires_at = _set_user_cooldown(
            cursor,
            user_id,
            "hunt",
            HUNT_COOLDOWN_SECONDS,
        )

    return {
        "hunting_serial": serial,
        "hunting_card_name": ERAS[era]["members"][member_code]["name"],
        "hunting_rarity": rarity,
        "skill": skills["skill"],
        "points": skills["points"],
        "cap": skills["cap"],
        "training_sessions": skills["training_sessions"],
        "training_bonus": progress,
        "reward_card": reward_card,
        "payout": payout,
        "new_balance": new_balance,
        "cooldown_until": expires_at,
    }


# Pagination for inventory
def build_spin_outcomes(wager_rarity):
    reward_counts = SPIN_REWARD_COUNTS[wager_rarity]
    outcomes = [
        rarity
        for rarity, count in reward_counts.items()
        for _ in range(count)
    ]
    outcomes.extend([None] * SPIN_BOMB_SLOTS)
    if len(outcomes) != SPIN_BOARD_SIZE:
        raise RuntimeError(
            f"Spin outcomes must fill exactly {SPIN_BOARD_SIZE} buttons."
        )
    random.shuffle(outcomes)
    return outcomes


def start_card_spin(user_id, serial):
    today = datetime.date.today().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            '''SELECT member_code, era, rarity, in_binder
               FROM cards WHERE serial=? AND owner_id=?''',
            (serial, user_id),
        )
        card_row = cursor.fetchone()
        if card_row is None:
            raise ValueError("You don't own a card with that serial anymore.")
        member_code, era, rarity, in_binder = card_row
        if in_binder:
            raise ValueError(
                "That card is in your binder. Remove it with "
                "`/binder remove` before spinning."
            )
        if rarity not in SPIN_REWARD_COUNTS:
            raise ValueError("That card has an unsupported rarity and can't be spun.")

        cursor.execute(
            "SELECT 1 FROM market_listings WHERE card_serial=?",
            (serial,),
        )
        if cursor.fetchone():
            raise ValueError(
                "Unlist that card from the market before using it for a spin."
            )

        cursor.execute(
            "SELECT spin_date, spins FROM spin_usage WHERE user_id=?",
            (user_id,),
        )
        usage_row = cursor.fetchone()
        spins_used = (
            usage_row[1]
            if usage_row and usage_row[0] == today
            else 0
        )
        if spins_used >= SPIN_DAILY_LIMIT:
            raise ValueError(
                f"You've used all **{SPIN_DAILY_LIMIT} spins** for today. "
                "Your limit resets at local midnight."
            )

        member = ERAS[era]["members"][member_code]
        wagered_card = {
            "serial": serial,
            "member_code": member_code,
            "era": era,
            "rarity": rarity,
            "name": member["name"],
            "full_name": member["full_name"],
        }
        outcomes = build_spin_outcomes(rarity)
        cursor.execute(
            "DELETE FROM cards WHERE serial=? AND owner_id=?",
            (serial, user_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("The wagered card changed before the spin started.")
        cursor.execute(
            "DELETE FROM card_skill_points WHERE card_serial=?",
            (serial,),
        )

        spins_used += 1
        cursor.execute(
            '''INSERT INTO spin_usage (user_id, spin_date, spins)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   spin_date=excluded.spin_date,
                   spins=excluded.spins''',
            (user_id, today, spins_used),
        )
        if spins_used == SPIN_DAILY_LIMIT:
            reset_at = next_local_midnight_timestamp(today)
            cursor.execute(
                '''INSERT OR REPLACE INTO cooldowns
                   (user_id, cooldown_type, expires_at)
                   VALUES (?, 'spin', ?)''',
                (user_id, reset_at),
            )
            schedule_cooldown_reminder(
                cursor,
                user_id,
                "spin",
                reset_at,
            )

    return wagered_card, outcomes, SPIN_DAILY_LIMIT - spins_used


MERGE_UPGRADES = {
    "Common": "Rare",
    "Rare": "Epic",
    "Epic": "Legendary",
}

def get_merge_selection(cursor, user_id, serials):
    required_count = len(serials)
    if required_count not in {9, 10}:
        raise ValueError("A merge requires 10 cards, or 9 with an activated Merge Discount Token.")
    if required_count == 9:
        cursor.execute(
            '''SELECT merge_discounts FROM user_item_effects
               WHERE user_id=?''',
            (user_id,),
        )
        discount = cursor.fetchone()
        if discount is None or discount[0] <= 0:
            raise ValueError(
                "You need to activate a Merge Discount Token with `/use` and `merge` "
                "before merging 9 cards."
            )

    placeholders = ",".join("?" for _ in serials)
    cursor.execute(
        f'''SELECT serial, member_code, era, rarity, owner_id, in_binder
            FROM cards WHERE serial IN ({placeholders})''',
        serials,
    )
    cards_by_serial = {row[0]: row for row in cursor.fetchall()}
    if len(cards_by_serial) != required_count:
        raise ValueError("One or more of those card serials could not be found.")

    selected_cards = [cards_by_serial[serial] for serial in serials]
    if any(card[4] != user_id for card in selected_cards):
        raise ValueError("You can only merge cards that you own.")
    binder_serials = [card[0] for card in selected_cards if card[5]]
    if binder_serials:
        raise ValueError(
            "Remove these cards from your binder before merging: "
            + ", ".join(f"`{serial}`" for serial in binder_serials)
        )

    selected_rarity = selected_cards[0][3]
    if any(card[3] != selected_rarity for card in selected_cards):
        raise ValueError(f"All {required_count} cards must have the same rarity.")
    if selected_rarity not in MERGE_UPGRADES:
        raise ValueError(
            f"{selected_rarity} cards cannot be merged into a higher rarity."
        )

    cursor.execute(
        f'''SELECT card_serial FROM market_listings
            WHERE card_serial IN ({placeholders})''',
        serials,
    )
    listed_serials = [row[0] for row in cursor.fetchall()]
    if listed_serials:
        raise ValueError(
            "Unlist these cards before merging them: "
            + ", ".join(f"`{serial}`" for serial in listed_serials)
        )

    return selected_rarity, selected_cards

def merge_owned_cards(user_id, serials):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        selected_rarity, _ = get_merge_selection(cursor, user_id, serials)
        if len(serials) == 9:
            cursor.execute(
                '''UPDATE user_item_effects
                   SET merge_discounts=merge_discounts-1
                   WHERE user_id=? AND merge_discounts>0''',
                (user_id,),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("The Merge Discount Token is no longer available.")
        merged_card = generate_card(
            forced_rarity=MERGE_UPGRADES[selected_rarity],
            connection=conn,
        )
        delete_placeholders = ",".join("?" for _ in serials)
        cursor.execute(
            f'''DELETE FROM cards
                WHERE owner_id=? AND serial IN ({delete_placeholders})''',
            [user_id, *serials],
        )
        if cursor.rowcount != len(serials):
            raise RuntimeError("The selected cards changed during the merge.")
        cursor.execute(
            f'''DELETE FROM card_skill_points
                WHERE card_serial IN ({delete_placeholders})''',
            serials,
        )

        cursor.execute(
            '''INSERT INTO cards
               (serial, member_code, era, rarity, owner_id, obtained_at)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (
                merged_card["serial"],
                merged_card["member_code"],
                merged_card["era"],
                merged_card["rarity"],
                user_id,
                str(datetime.datetime.now()),
            ),
        )

    return merged_card


def format_target(target):
    member_data = ERAS.get(target["era"], {}).get("members", {}).get(
        target["member_code"]
    )
    if member_data is None:
        member_data = next(
            (
                era_data["members"][target["member_code"]]
                for era_data in ERAS.values()
                if target["member_code"] in era_data["members"]
            ),
            None,
        )
    if member_data is None:
        return "Unknown member"

    parts = []
    if target["rarity"]:
        parts.append(target["rarity"])
    parts.append(member_data["full_name"])
    if target["era"]:
        parts.append(ERAS[target["era"]]["name"])
    else:
        parts.append("any era")
    return " ".join(parts)

def parse_biases(query):
    """Resolve bias names, short names, and member codes in the supplied order."""
    aliases = {}
    for index, member_code in enumerate(S_ORDER, start=1):
        member_data = S_MEMBERS[member_code]
        for alias in (
            member_code,
            f"s{index}",
            member_data["name"],
            member_data["full_name"],
        ):
            normalized_alias = alias.casefold().split()
            aliases[tuple(normalized_alias)] = member_code

    tokens = query.casefold().replace(",", " ").split()
    matched_codes = []
    position = 0
    while position < len(tokens):
        matches = [
            (alias_tokens, member_code)
            for alias_tokens, member_code in aliases.items()
            if tokens[position:position + len(alias_tokens)] == list(alias_tokens)
        ]
        if not matches:
            raise ValueError(f"Couldn't identify bias name starting with `{tokens[position]}`.")

        alias_tokens, member_code = max(matches, key=lambda match: len(match[0]))
        matched_codes.append(member_code)
        position += len(alias_tokens)

    return sorted(set(matched_codes), key=S_ORDER.index)
