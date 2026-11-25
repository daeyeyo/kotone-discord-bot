import sqlite3
from typing import Literal

import discord

from eras import ERAS
from kotone.client import (
    format_fallback_display_name,
    is_placeholder_username,
    resolve_discord_user_info,
    slash_command,
)
from kotone.config import RARITIES, S_MEMBERS, S_ORDER
from kotone.db import (
    get_db,
    sync_user_username,
)
from kotone.game import get_user_target


LEADERBOARD_PAGE_SIZE = 10
MAX_LIVE_USER_FETCHES = 10
DEFAULT_ERA = "ASSEMBLE24"
DEFAULT_MEMBER = "KTN"
BOARD_ORDER = ("global", "member", "era")
ERA_ORDER = {
    era_code: index for index, era_code in enumerate(ERAS)
}
MEMBER_ERAS = {
    member_code: frozenset(
        era_code
        for era_code, era_data in ERAS.items()
        if member_code in era_data["members"]
    )
    for member_code in S_MEMBERS
}


def _pluralize(count, singular, plural=None):
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {plural or singular + 's'}"


def _new_user_info(user_id, username, display_name=None):
    return {
        "user_id": user_id,
        "username": username,
        "display_name": display_name,
        "cards": {},
    }


def fetch_leaderboard_rows():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT owner_id, era, member_code, rarity, COUNT(*)
               FROM cards
               WHERE owner_id IS NOT NULL
               GROUP BY owner_id, era, member_code, rarity'''
        )
        card_rows = cursor.fetchall()
        cursor.execute("SELECT user_id, username, display_name FROM users")
        user_rows = cursor.fetchall()
    return card_rows, user_rows


def build_user_stats(card_rows, user_rows):
    stats = {}
    for user_id, username, display_name in user_rows:
        stats[user_id] = _new_user_info(user_id, username, display_name)

    for owner_id, era, member_code, rarity, copies in card_rows:
        info = stats.get(owner_id)
        if info is None:
            info = _new_user_info(owner_id, None, None)
            stats[owner_id] = info
        info["cards"][(era, member_code, rarity)] = copies

    return stats


async def build_display_names(ctx, stats, user_ids):
    names = {}
    fetch_budget = [MAX_LIVE_USER_FETCHES]
    for user_id in sorted(user_ids):
        info = stats.get(user_id)
        stored_name = info["username"] if info else None
        stored_display_name = info["display_name"] if info else None
        display_name, fetched_names, _ = await resolve_discord_user_info(
            ctx.bot,
            user_id,
            guild=ctx.guild,
            stored_display_name=stored_display_name,
            stored_username=stored_name,
            fetch_budget=fetch_budget,
        )
        names[user_id] = discord.utils.escape_markdown(display_name)
        if fetched_names is not None:
            fetched_display, fetched_username = fetched_names
            sync_user_username(
                user_id,
                username=fetched_username,
                display_name=fetched_display,
            )
    return names


def _entry(
    rank,
    info,
    names,
    primary,
    secondary,
    value,
    tiebreak_value,
):
    if info.get("display_name") and not is_placeholder_username(info["display_name"]):
        fallback_name = info["display_name"]
    elif info.get("username") and not is_placeholder_username(info["username"]):
        fallback_name = info["username"]
    else:
        fallback_name = format_fallback_display_name(info["user_id"])
    return {
        "rank": rank,
        "user_id": info["user_id"],
        "name": names.get(
            info["user_id"],
            fallback_name,
        ),
        "primary": primary,
        "secondary": secondary,
        "value": value,
        "tiebreak_value": tiebreak_value,
    }


def _chase_note(
    entries,
    viewer_id,
    metric,
    tiebreak_singular="copy",
    tiebreak_plural="copies",
):
    viewer_index = next(
        (
            index
            for index, entry in enumerate(entries)
            if entry["user_id"] == viewer_id
        ),
        None,
    )
    if viewer_index is None:
        return None
    if viewer_index == 0:
        return "You are #1 — defend your spot!"

    viewer = entries[viewer_index]
    ahead = entries[viewer_index - 1]
    gap = ahead["value"] - viewer["value"]
    if gap:
        unit = metric if gap == 1 else f"{metric}s"
        return (
            f"{gap} {unit} behind #{ahead['rank']} "
            f"{ahead['name']}."
        )

    copy_gap = ahead["tiebreak_value"] - viewer["tiebreak_value"]
    if copy_gap:
        unit = tiebreak_singular if copy_gap == 1 else tiebreak_plural
        return (
            f"Tied with #{ahead['rank']} {ahead['name']} on {metric}s — "
            f"{copy_gap} more {unit} would pass them."
        )
    return (
        f"Tied with #{ahead['rank']} {ahead['name']} — "
        "keep collecting!"
    )


def build_global_board(stats, names, viewer_id):
    scored = []
    for info in stats.values():
        total_cards = sum(info["cards"].values())
        if total_cards:
            scored.append((total_cards, len(info["cards"]), info))

    scored.sort(
        key=lambda item: (
            -item[0],
            -item[1],
            item[2]["user_id"],
        )
    )
    entries = [
        _entry(
            rank,
            info,
            names,
            _pluralize(total_cards, "card"),
            _pluralize(unique_count, "unique card"),
            total_cards,
            unique_count,
        )
        for rank, (total_cards, unique_count, info) in enumerate(scored, 1)
    ]
    return {
        "label": "Total Cards",
        "title": "🌐 Global Card Collection",
        "description": (
            "Ranked by total cards owned, including duplicates. Unique cards "
            "break ties. This board combines players across all servers."
        ),
        "entries": entries,
        "empty": "No cards have been collected yet.",
        "unranked": "Collect a card to enter the global leaderboard.",
        "chase": _chase_note(
            entries,
            viewer_id,
            "card",
            "unique card",
            "unique cards",
        ),
    }


def build_member_board(stats, names, member_code, viewer_id):
    member_name = S_MEMBERS[member_code]["name"]
    member_eras = MEMBER_ERAS[member_code]
    total_slots = len(member_eras) * len(RARITIES)
    scored = []

    for info in stats.values():
        groups = [
            (era, rarity, copies)
            for (era, card_member, rarity), copies in info["cards"].items()
            if card_member == member_code
        ]
        if not groups:
            continue

        unique_count = len(groups)
        total_copies = sum(copies for _, _, copies in groups)
        scored.append((total_copies, unique_count, info))

    scored.sort(
        key=lambda item: (
            -item[0],
            -item[1],
            item[2]["user_id"],
        )
    )

    entries = []
    for rank, (total_copies, unique_count, info) in enumerate(scored, 1):
        complete = total_slots > 0 and unique_count >= total_slots
        percentage = unique_count / total_slots if total_slots else 0.0
        entries.append(
            _entry(
                rank,
                info,
                names,
                _pluralize(total_copies, "card"),
                (
                    f"{unique_count}/{total_slots} unique "
                    f"({percentage:.0%})"
                    + (" • ✅ Complete" if complete else "")
                ),
                total_copies,
                unique_count,
            )
        )

    era_count = len(member_eras)
    return {
        "label": "Member Cards",
        "title": f"💖 Member Collection • {member_name}",
        "description": (
            f"Ranked by total **{member_name}** cards, including duplicates. "
            f"Unique cards break ties. Collect all **{total_slots}** unique "
            f"cards across {era_count} "
            f"{'era' if era_count == 1 else 'eras'} for a completion badge."
        ),
        "entries": entries,
        "empty": f"No one owns a {member_name} card yet.",
        "unranked": f"Collect a {member_name} card to enter this leaderboard.",
        "chase": _chase_note(
            entries,
            viewer_id,
            "member card",
            "unique card",
            "unique cards",
        ),
    }


def build_era_board(stats, names, era, viewer_id):
    era_name = ERAS[era]["name"]
    total_slots = len(ERAS[era]["members"]) * len(RARITIES)
    scored = []

    for info in stats.values():
        groups = [
            (member_code, rarity, copies)
            for (card_era, member_code, rarity), copies
            in info["cards"].items()
            if card_era == era
        ]
        if not groups:
            continue

        unique_count = len(groups)
        total_copies = sum(copies for _, _, copies in groups)
        scored.append((unique_count, total_copies, info))

    scored.sort(
        key=lambda item: (
            -item[0],
            -item[1],
            item[2]["user_id"],
        )
    )

    entries = []
    for rank, (unique_count, total_copies, info) in enumerate(scored, 1):
        percentage = unique_count / total_slots if total_slots else 0.0
        complete = total_slots > 0 and unique_count >= total_slots
        entries.append(
            _entry(
                rank,
                info,
                names,
                (
                    f"{unique_count}/{total_slots} slots "
                    f"({percentage:.0%})"
                    + (" • ✅ Complete" if complete else "")
                ),
                _pluralize(total_copies, "copy", "copies"),
                unique_count,
                total_copies,
            )
        )

    return {
        "label": "Era",
        "title": f"📚 Era Completion • {era_name}",
        "description": (
            f"Ranked by unique (member, rarity) slots filled in "
            f"**{era_name}**. More copies break ties.\n"
            "Defaults come from /target, then your most-collected era."
        ),
        "entries": entries,
        "empty": f"No one owns a {era_name} card yet.",
        "unranked": f"Collect a {era_name} card to enter Era Completion.",
        "chase": _chase_note(entries, viewer_id, "era slot"),
    }


def _most_collected_member(user_id, stats):
    info = stats.get(user_id)
    if info is None:
        return None

    member_counts = {}
    for _, member_code, _ in info["cards"]:
        member_counts[member_code] = member_counts.get(member_code, 0) + 1
    if not member_counts:
        return None

    return max(
        member_counts,
        key=lambda code: (
            member_counts[code],
            -S_ORDER.index(code),
        ),
    )


def _most_collected_era(user_id, stats):
    info = stats.get(user_id)
    if info is None:
        return None

    era_counts = {}
    for era_code, _, _ in info["cards"]:
        era_counts[era_code] = era_counts.get(era_code, 0) + 1
    if not era_counts:
        return None

    return max(
        era_counts,
        key=lambda code: (
            era_counts[code],
            -ERA_ORDER.get(code, 0),
        ),
    )


def resolve_member_code(ctx, member_name, stats):
    if member_name:
        normalized_name = " ".join(member_name.casefold().split())
        for member_code, member_data in S_MEMBERS.items():
            member_names = {
                member_code.casefold(),
                member_data["name"].casefold(),
                " ".join(member_data["full_name"].casefold().split()),
            }
            if normalized_name in member_names:
                return member_code
        raise ValueError(f"I couldn't find a tripleS member matching `{member_name}`.")

    target = get_user_target(ctx.author.id)
    if target and target.get("member_code") in S_MEMBERS:
        return target["member_code"]

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT member_code FROM user_biases WHERE user_id=?",
            (ctx.author.id,),
        )
        bias_codes = {row[0] for row in cursor.fetchall()}
    for member_code in S_ORDER:
        if member_code in bias_codes:
            return member_code

    collected_member = _most_collected_member(ctx.author.id, stats)
    return collected_member or DEFAULT_MEMBER


def resolve_era_code(ctx, era_name, stats):
    if era_name in ERAS:
        return era_name

    target = get_user_target(ctx.author.id)
    if target and target.get("era") in ERAS:
        return target["era"]

    collected_era = _most_collected_era(ctx.author.id, stats)
    return collected_era or DEFAULT_ERA


class LeaderboardView(discord.ui.View):
    def __init__(self, user_id, boards, board_order, initial_board, page_size=10):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.boards = boards
        self.current_board = initial_board
        self.page_size = page_size

        for board_key in board_order:
            button = discord.ui.Button(
                label=boards[board_key]["label"],
                style=(
                    discord.ButtonStyle.primary
                    if board_key == initial_board
                    else discord.ButtonStyle.secondary
                ),
                custom_id=f"leaderboard:{board_key}",
            )
            button.callback = self._select_board(board_key)
            self.add_item(button)

    def _select_board(self, board_key):
        async def callback(interaction):
            self.current_board = board_key
            for button in self.children:
                button.style = (
                    discord.ButtonStyle.primary
                    if button.custom_id == f"leaderboard:{board_key}"
                    else discord.ButtonStyle.secondary
                )
            await interaction.response.edit_message(
                embed=self.get_embed(),
                view=self,
            )

        return callback

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the player who opened this leaderboard can use it.",
                ephemeral=True,
            )
            return False
        return True

    def get_embed(self):
        board = self.boards[self.current_board]
        entries = board["entries"]
        displayed_entries = entries[:self.page_size]
        if displayed_entries:
            lines = [
                f"**#{entry['rank']} {entry['name']}** — "
                f"{entry['primary']} • {entry['secondary']}"
                for entry in displayed_entries
            ]
            description = f"{board['description']}\n\n" + "\n".join(lines)
        else:
            description = f"{board['description']}\n\n{board['empty']}"

        embed = discord.Embed(
            title=board["title"],
            description=description,
            color=0xff6b8b,
        )
        viewer_entry = next(
            (
                entry for entry in entries
                if entry["user_id"] == self.user_id
            ),
            None,
        )
        if viewer_entry is None:
            embed.set_footer(text=board["unranked"])
        elif viewer_entry not in displayed_entries:
            embed.set_footer(
                text=(
                    f"Your rank: #{viewer_entry['rank']} • "
                    f"{board['chase'] or 'Keep collecting!'}"
                )
            )
        elif board["chase"]:
            embed.set_footer(text=board["chase"])
        return embed


@slash_command(name="leaderboard")
async def leaderboard(
    ctx,
    board: Literal["global", "member", "era"] = None,
    member: str = None,
    era: Literal["AAA", "ASSEMBLE", "ASSEMBLE24", "KRE", "VV"] = None,
):
    """View global card, member collection, and era completion leaderboards."""
    try:
        card_rows, user_rows = fetch_leaderboard_rows()
        stats = build_user_stats(card_rows, user_rows)
        member_code = resolve_member_code(ctx, member, stats)
        era_code = resolve_era_code(ctx, era, stats)
    except ValueError as error:
        await ctx.reply(str(error))
        return
    except sqlite3.Error as error:
        print(f"Database error while loading leaderboards: {error}")
        await ctx.reply(
            "The leaderboard couldn't be loaded due to a database error."
        )
        return

    boards = {
        "global": build_global_board(
            stats,
            {},
            ctx.author.id,
        ),
        "member": build_member_board(
            stats,
            {},
            member_code,
            ctx.author.id,
        ),
        "era": build_era_board(
            stats,
            {},
            era_code,
            ctx.author.id,
        ),
    }
    display_user_ids = {
        entry["user_id"]
        for current_board in boards.values()
        for entry in current_board["entries"][:LEADERBOARD_PAGE_SIZE]
    }
    for current_board in boards.values():
        entries = current_board["entries"]
        for index, entry in enumerate(entries):
            if entry["user_id"] == ctx.author.id:
                display_user_ids.add(entry["user_id"])
                if index > 0:
                    display_user_ids.add(entries[index - 1]["user_id"])
                break
    names = await build_display_names(ctx, stats, display_user_ids)
    for current_board in boards.values():
        for entry in current_board["entries"]:
            if entry["user_id"] in names:
                entry["name"] = names[entry["user_id"]]
    for board_name, metric, tie_singular, tie_plural in (
        ("global", "card", "unique card", "unique cards"),
        ("member", "member card", "unique card", "unique cards"),
        ("era", "era slot", "copy", "copies"),
    ):
        boards[board_name]["chase"] = _chase_note(
            boards[board_name]["entries"],
            ctx.author.id,
            metric,
            tie_singular,
            tie_plural,
        )

    if board in boards:
        initial_board = board
    elif member:
        initial_board = "member"
    elif era:
        initial_board = "era"
    else:
        initial_board = "global"
    view = LeaderboardView(
        ctx.author.id,
        boards,
        BOARD_ORDER,
        initial_board,
        page_size=LEADERBOARD_PAGE_SIZE,
    )
    view.message = await ctx.reply(embed=view.get_embed(), view=view)
