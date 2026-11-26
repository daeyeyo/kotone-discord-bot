import sqlite3
import discord
from discord import app_commands
from discord.ui import View
from eras import (
    ERAS,
    ERA_ALIASES,
    ERA_ALIAS_LOOKUP,
    normalize_era_alias,
)
from kotone.client import (
    SLASH_COMMANDS,
    bot,
    slash_command,
)
from kotone.config import (
    RARITIES,
    S_MEMBERS,
    S_ORDER,
)
from kotone.db import (
    get_db,
)

BINDER_PAGE_SIZE = 5

binder_group = app_commands.Group(
    name="binder",
    description=(
        "Protect cards from giving, listing, merging, and spinning. "
        "Use /binder list to view protected cards."
    ),
)

ERA_ORDER = {era_code: index for index, era_code in enumerate(ERAS)}
MEMBER_ORDER = {
    member_code: index for index, member_code in enumerate(S_ORDER)
}
RARITY_ORDER = {
    rarity_name: index for index, rarity_name in enumerate(RARITIES)
}


def _pluralize(count, singular, plural=None):
    if count == 1:
        return singular
    return plural or f"{singular}s"


def _binder_embed(description, title="Binder"):
    return discord.Embed(
        title=title,
        description=description,
        color=0xff6b8b,
    )


async def _reply_binder(ctx, description, title="Binder"):
    await ctx.reply(
        embed=_binder_embed(description, title),
        ephemeral=True,
    )


def _normalize_member(value):
    normalized = " ".join(value.casefold().split())
    for member_code in S_ORDER:
        member_data = S_MEMBERS[member_code]
        if normalized in {
            member_code.casefold(),
            member_data["name"].casefold(),
            " ".join(member_data["full_name"].casefold().split()),
        }:
            return member_code
    return None


def _resolve_group(value):
    resolved = ERA_ALIAS_LOOKUP.get(normalize_era_alias(value.strip()))
    return resolved if resolved in ERAS else None


def _resolve_tier(value):
    normalized = value.strip().casefold()
    for rarity_name in RARITIES:
        if normalized == rarity_name.casefold():
            return rarity_name
    return None


def _format_card(serial, member_code, era, rarity):
    try:
        member_name = ERAS[era]["members"][member_code]["name"]
        era_name = ERAS[era]["name"]
    except KeyError:
        return f"`{serial}`"
    return f"**{rarity} {member_name}** (`{serial}`, {era_name})"


def _parse_target(serial, member, group, tier):
    provided = [
        value
        for value in (serial, member, group, tier)
        if value is not None and value.strip()
    ]
    if not provided:
        raise ValueError(
            "Choose one target: a card serial, member, group/unit/theme, "
            "or tier."
        )
    if len(provided) > 1:
        raise ValueError(
            "Choose exactly one target: a card serial, member, "
            "group/unit/theme, or tier."
        )

    if serial is not None and serial.strip():
        serial = serial.strip()
        if len(serial) > 50:
            raise ValueError("That card serial is too long.")
        return {"type": "serial", "value": serial}

    if member is not None and member.strip():
        member_code = _normalize_member(member)
        if member_code is None:
            raise ValueError(
                f"I couldn't find a tripleS member matching `{member}`."
            )
        return {"type": "member", "value": member_code}

    if group is not None and group.strip():
        era = _resolve_group(group)
        if era is None:
            raise ValueError(
                f"I couldn't identify `{group}` as a group, unit, theme, "
                "or season."
            )
        return {"type": "group", "value": era}

    tier_name = _resolve_tier(tier)
    if tier_name is None:
        raise ValueError(f"I couldn't identify `{tier}` as a tier.")
    return {"type": "tier", "value": tier_name}


def _target_label(target):
    target_type = target["type"]
    value = target["value"]
    if target_type == "serial":
        return f"the card `{value}`"
    if target_type == "member":
        return f"all **{S_MEMBERS[value]['name']}** cards"
    if target_type == "group":
        return f"all **{ERAS[value]['name']}** cards"
    return f"all **{value}** cards"


def _target_clause(target, alias=""):
    prefix = f"{alias}." if alias else ""
    columns = {
        "serial": "serial",
        "member": "member_code",
        "group": "era",
        "tier": "rarity",
    }
    return f"{prefix}{columns[target['type']]} = ?", [target["value"]]


def _get_add_candidates(user_id, target):
    clause, params = _target_clause(target, "c")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f'''SELECT c.serial, c.in_binder,
                       m.card_serial IS NOT NULL AS listed
                FROM cards c
                LEFT JOIN market_listings m ON m.card_serial=c.serial
                WHERE c.owner_id=? AND {clause}''',
            [user_id, *params],
        )
        rows = cursor.fetchall()

    eligible = [
        serial
        for serial, in_binder, listed in rows
        if not in_binder and not listed
    ]
    listed = sum(
        1 for _, in_binder, is_listed in rows if not in_binder and is_listed
    )
    bound = sum(1 for _, in_binder, _ in rows if in_binder)
    return eligible, listed, bound


def _get_remove_candidates(user_id, target):
    clause, params = _target_clause(target, "c")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f'''SELECT c.serial FROM cards c
                WHERE c.owner_id=? AND c.in_binder=1 AND {clause}''',
            [user_id, *params],
        )
        return [row[0] for row in cursor.fetchall()]


def _apply_cards(user_id, action, serials):
    if not serials:
        return 0

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        changed = 0
        if action == "add":
            for serial in serials:
                cursor.execute(
                    '''UPDATE cards SET in_binder=1
                       WHERE serial=? AND owner_id=? AND in_binder=0
                         AND NOT EXISTS (
                             SELECT 1 FROM market_listings m
                             WHERE m.card_serial=cards.serial
                         )''',
                    (serial, user_id),
                )
                changed += cursor.rowcount
        else:
            for serial in serials:
                cursor.execute(
                    '''UPDATE cards SET in_binder=0
                       WHERE serial=? AND owner_id=? AND in_binder=1''',
                    (serial, user_id),
                )
                changed += cursor.rowcount
        conn.commit()
    return changed


def _autocomplete_owned_serials(interaction, current, binder_only=False):
    query = '''
        SELECT c.serial, c.member_code, c.era, c.rarity, c.in_binder,
               m.card_serial IS NOT NULL AS listed
        FROM cards c
        LEFT JOIN market_listings m ON m.card_serial = c.serial
        WHERE c.owner_id=?
    '''
    params = [interaction.user.id]
    if binder_only:
        query += " AND c.in_binder=1"
    current = (current or "").strip()
    if current:
        query += " AND c.serial LIKE ?"
        params.append(f"%{current}%")
    query += " ORDER BY c.in_binder, c.obtained_at DESC LIMIT 25"

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
    except sqlite3.Error as error:
        print(f"Database error while loading binder autocomplete: {error}")
        return []

    choices = []
    for serial, member_code, era, rarity, in_binder, listed in rows:
        try:
            member_name = ERAS[era]["members"][member_code]["name"]
        except KeyError:
            member_name = member_code
        status = []
        if in_binder:
            status.append("binder")
        if listed:
            status.append("listed")
        suffix = f" • {', '.join(status)}" if status else ""
        choices.append(
            app_commands.Choice(
                name=(
                    f"{serial} • {member_name} • {rarity}{suffix}"
                )[:100],
                value=serial,
            )
        )
    return choices


async def _add_serial_autocomplete(interaction, current):
    return _autocomplete_owned_serials(interaction, current)


async def _remove_serial_autocomplete(interaction, current):
    return _autocomplete_owned_serials(interaction, current, binder_only=True)


async def _member_autocomplete(interaction, current):
    current = " ".join((current or "").casefold().split())
    choices = []
    for member_code in S_ORDER:
        member_data = S_MEMBERS[member_code]
        searchable = {
            member_code.casefold(),
            member_data["name"].casefold(),
            " ".join(member_data["full_name"].casefold().split()),
        }
        if current and not any(current in value for value in searchable):
            continue
        choices.append(
            app_commands.Choice(
                name=f"{member_data['name']} ({member_code})",
                value=member_code,
            )
        )
        if len(choices) >= 25:
            break
    return choices


async def _group_autocomplete(interaction, current):
    current = (current or "").casefold()
    choices = []
    for era_code in ERAS:
        aliases = ERA_ALIASES.get(era_code, (era_code,))
        searchable = " ".join(aliases).casefold()
        if current and current not in searchable and current not in era_code.casefold():
            continue
        choices.append(app_commands.Choice(name=era_code, value=era_code))
    return choices


async def _tier_autocomplete(interaction, current):
    current = (current or "").casefold()
    return [
        app_commands.Choice(name=f"{rarity_name} tier", value=rarity_name)
        for rarity_name in RARITIES
        if not current or current in rarity_name.casefold()
    ]


class BinderConfirmationView(View):
    def __init__(self, user_id, action, serials):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.action = action
        self.serials = serials
        self.resolved = False
        self.message = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the person who started this binder change can confirm it.",
                ephemeral=True,
            )
            return False
        return True

    def disable_buttons(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction, button):
        if self.resolved:
            await interaction.response.send_message(
                "This binder confirmation has already ended.",
                ephemeral=True,
            )
            return
        self.resolved = True
        self.disable_buttons()

        try:
            changed = _apply_cards(self.user_id, self.action, self.serials)
        except sqlite3.Error as error:
            print(f"Database error while updating binder: {error}")
            await interaction.response.edit_message(
                embed=_binder_embed(
                    "The binder couldn't be updated due to a database error.",
                    "Binder Update Failed",
                ),
                view=None,
            )
            self.stop()
            return

        if changed:
            if self.action == "add":
                result = f"Added **{changed}** {_pluralize(changed, 'card')} to your binder."
                title = "Cards Added"
            else:
                result = (
                    f"Removed **{changed}** "
                    f"{_pluralize(changed, 'card')} from your binder."
                )
                title = "Cards Removed"
            if changed < len(self.serials):
                skipped = len(self.serials) - changed
                result += (
                    f"\n{skipped} {_pluralize(skipped, 'card')} "
                    "changed while the confirmation was open and was skipped."
                )
        else:
            if self.action == "add":
                result = (
                    "No cards were added. They may be listed or already in "
                    "your binder."
                )
            else:
                result = "No cards were removed. They may no longer be in your binder."
            title = "No Cards Changed"

        await interaction.response.edit_message(
            embed=_binder_embed(result, title),
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction, button):
        if self.resolved:
            await interaction.response.send_message(
                "This binder confirmation has already ended.",
                ephemeral=True,
            )
            return
        self.resolved = True
        self.disable_buttons()
        await interaction.response.edit_message(
            embed=_binder_embed("Binder change cancelled."),
            view=None,
        )
        self.stop()

    async def on_timeout(self):
        if self.resolved:
            return
        self.resolved = True
        self.disable_buttons()
        if self.message is not None:
            try:
                await self.message.edit(
                    embed=_binder_embed(
                        "Binder confirmation expired. Nothing was changed."
                    ),
                    view=self,
                )
            except discord.HTTPException:
                pass


class BinderView(View):
    def __init__(self, cards, user, filter_labels=None):
        super().__init__(timeout=180)
        self.cards = cards
        self.user = user
        self.filter_labels = filter_labels or []
        self.page = 0
        self.message = None
        self.update_buttons()

    @property
    def total_pages(self):
        return max(
            1,
            (len(self.cards) + BINDER_PAGE_SIZE - 1) // BINDER_PAGE_SIZE,
        )

    def update_buttons(self):
        self.children[0].disabled = self.page == 0
        self.children[1].disabled = self.page >= self.total_pages - 1

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "Only the person who opened this binder can use it.",
                ephemeral=True,
            )
            return False
        return True

    def get_embed(self):
        description = (
            f"Page {self.page + 1}/{self.total_pages} • "
            f"Protected cards: {len(self.cards)}"
        )
        if self.filter_labels:
            description += "\nFilters: " + " • ".join(self.filter_labels)

        embed = discord.Embed(
            title=f"{self.user.display_name}'s Binder",
            description=description,
            color=0xff6b8b,
        )
        embed.set_author(
            name="Protected cards",
            icon_url=self.user.display_avatar.url,
        )

        start = self.page * BINDER_PAGE_SIZE
        end = min(start + BINDER_PAGE_SIZE, len(self.cards))
        for serial, member_code, era, rarity, obtained_at in self.cards[start:end]:
            try:
                member_name = ERAS[era]["members"][member_code]["name"]
                era_name = ERAS[era]["name"]
            except KeyError:
                member_name = "Unknown"
                era_name = "Unknown"
            embed.add_field(
                name=serial,
                value=(
                    f"Member: {member_name}\n"
                    f"Era: {era_name}\n"
                    f"Tier: {rarity}\n"
                    f"Obtained: {obtained_at[:10] if obtained_at else 'Unknown'}"
                ),
                inline=False,
            )

        embed.set_footer(
            text=(
                "Binder cards cannot be given, listed on the market, "
                "merged, or spun."
            )
        )
        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction, button):
        self.page = max(0, self.page - 1)
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.get_embed(),
            view=self,
        )

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction, button):
        self.page = min(self.total_pages - 1, self.page + 1)
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.get_embed(),
            view=self,
        )

    async def on_timeout(self):
        self.disable_buttons()
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


@slash_command(
    name="add",
    group=binder_group,
    autocomplete={
        "serial": _add_serial_autocomplete,
        "member": _member_autocomplete,
        "era": _group_autocomplete,
        "tier": _tier_autocomplete,
    },
    descriptions={
        "serial": "Protect one owned card by serial.",
        "member": "Protect every owned card for one member.",
        "era": "Protect every owned card in an era.",
        "tier": "Protect every owned card of one rarity tier.",
    },
)
async def binder_add(
    ctx,
    serial: str = None,
    member: str = None,
    era: str = None,
    tier: str = None,
):
    """Protect every owned card in an era."""
    try:
        target = _parse_target(serial, member, era, tier)
    except ValueError as error:
        await _reply_binder(ctx, str(error), "Invalid Binder Target")
        return

    if target["type"] == "serial":
        serial = target["value"]
        reply_args = None
        changed = 0
        card = None
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''SELECT owner_id, member_code, era, rarity, in_binder
                       FROM cards WHERE serial=?''',
                    (serial,),
                )
                card = cursor.fetchone()
                if card is None:
                    reply_args = ("Card not found.", "Card Not Found")
                elif card[0] != ctx.author.id:
                    reply_args = ("You don't own that card.", "Not Your Card")
                elif card[4]:
                    reply_args = (
                        f"{_format_card(serial, card[1], card[2], card[3])} "
                        "is already in your binder.",
                        "Already Protected",
                    )
                else:
                    cursor.execute(
                        "SELECT 1 FROM market_listings WHERE card_serial=?",
                        (serial,),
                    )
                    if cursor.fetchone():
                        reply_args = (
                            "That card is listed on the market. Unlist it with "
                            "`/unlist` before adding it to your binder.",
                            "Card Is Listed",
                        )
                    else:
                        cursor.execute("BEGIN IMMEDIATE")
                        cursor.execute(
                            '''UPDATE cards SET in_binder=1
                               WHERE serial=? AND owner_id=? AND in_binder=0
                                 AND NOT EXISTS (
                                     SELECT 1 FROM market_listings m
                                     WHERE m.card_serial=cards.serial
                                 )''',
                            (serial, ctx.author.id),
                        )
                        changed = cursor.rowcount
                        conn.commit()
        except sqlite3.Error as error:
            print(f"Database error while adding card to binder: {error}")
            await _reply_binder(
                ctx,
                "The card couldn't be added due to a database error.",
                "Binder Update Failed",
            )
            return

        if reply_args is not None:
            await _reply_binder(ctx, reply_args[0], reply_args[1])
            return

        if changed:
            await _reply_binder(
                ctx,
                f"Added {_format_card(serial, card[1], card[2], card[3])} "
                "to your binder.",
                "Card Protected",
            )
        else:
            await _reply_binder(
                ctx,
                "That card couldn't be added. It may have just been listed "
                "or changed.",
                "Card Not Changed",
            )
        return

    try:
        eligible_serials, listed, bound = _get_add_candidates(
            ctx.author.id,
            target,
        )
    except sqlite3.Error as error:
        print(f"Database error while checking binder additions: {error}")
        await _reply_binder(
            ctx,
            "The binder change couldn't be checked due to a database error.",
            "Binder Check Failed",
        )
        return

    eligible = len(eligible_serials)
    if not eligible:
        details = []
        if listed:
            details.append(
                f"**{listed}** matching {_pluralize(listed, 'card is', 'cards are')} "
                "listed on the market; unlist them first."
            )
        if bound:
            details.append(
                f"**{bound}** matching {_pluralize(bound, 'card is', 'cards are')} "
                "already in your binder."
            )
        await _reply_binder(
            ctx,
            "No cards were added. "
            + (" ".join(details) if details else "No matching cards were found."),
            "No Cards Added",
        )
        return

    label = _target_label(target)
    embed = discord.Embed(
        title="Confirm Binder Add",
        description=(
            f"Protect {label} in your binder?\n\n"
            f"This will add **{eligible}** "
            f"{_pluralize(eligible, 'card')}. "
            "Binder cards cannot be given, listed, merged, or spun. "
            "Market-listed cards are skipped."
        ),
        color=0xff6b8b,
    )
    if listed:
        embed.add_field(
            name="Skipped listings",
            value=(
                f"**{listed}** matching "
                f"{_pluralize(listed, 'card is', 'cards are')} listed on the "
                "market and will not be added."
            ),
            inline=False,
        )

    view = BinderConfirmationView(ctx.author.id, "add", eligible_serials)
    view.message = await ctx.reply(
        embed=embed,
        view=view,
        ephemeral=True,
    )


@slash_command(
    name="remove",
    group=binder_group,
    autocomplete={
        "serial": _remove_serial_autocomplete,
        "member": _member_autocomplete,
        "group": _group_autocomplete,
        "tier": _tier_autocomplete,
    },
    descriptions={
        "serial": "Remove one protected card by serial.",
        "member": "Remove every protected card for one member.",
        "group": "Remove every protected card in a group, unit, theme, or season.",
        "tier": "Remove every protected card of one rarity tier.",
    },
)
async def binder_remove(
    ctx,
    serial: str = None,
    member: str = None,
    group: str = None,
    tier: str = None,
):
    """Remove one card or a matching set of cards from your binder."""
    try:
        target = _parse_target(serial, member, group, tier)
    except ValueError as error:
        await _reply_binder(ctx, str(error), "Invalid Binder Target")
        return

    if target["type"] == "serial":
        serial = target["value"]
        reply_args = None
        changed = 0
        card = None
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''SELECT owner_id, member_code, era, rarity, in_binder
                       FROM cards WHERE serial=?''',
                    (serial,),
                )
                card = cursor.fetchone()
                if card is None:
                    reply_args = ("Card not found.", "Card Not Found")
                elif card[0] != ctx.author.id:
                    reply_args = ("You don't own that card.", "Not Your Card")
                elif not card[4]:
                    reply_args = (
                        f"{_format_card(serial, card[1], card[2], card[3])} "
                        "is not in your binder.",
                        "Not Protected",
                    )
                else:
                    cursor.execute("BEGIN IMMEDIATE")
                    cursor.execute(
                        '''UPDATE cards SET in_binder=0
                           WHERE serial=? AND owner_id=? AND in_binder=1''',
                        (serial, ctx.author.id),
                    )
                    changed = cursor.rowcount
                    conn.commit()
        except sqlite3.Error as error:
            print(f"Database error while removing card from binder: {error}")
            await _reply_binder(
                ctx,
                "The card couldn't be removed due to a database error.",
                "Binder Update Failed",
            )
            return

        if reply_args is not None:
            await _reply_binder(ctx, reply_args[0], reply_args[1])
            return

        if changed:
            await _reply_binder(
                ctx,
                f"Removed {_format_card(serial, card[1], card[2], card[3])} "
                "from your binder.",
                "Card Unprotected",
            )
        else:
            await _reply_binder(
                ctx,
                "That card is no longer in your binder.",
                "Card Not Changed",
            )
        return

    try:
        serials = _get_remove_candidates(ctx.author.id, target)
    except sqlite3.Error as error:
        print(f"Database error while checking binder removals: {error}")
        await _reply_binder(
            ctx,
            "The binder change couldn't be checked due to a database error.",
            "Binder Check Failed",
        )
        return

    count = len(serials)
    if count == 0:
        await _reply_binder(
            ctx,
            "No binder cards match that target.",
            "No Cards Found",
        )
        return

    label = _target_label(target)
    embed = discord.Embed(
        title="Confirm Binder Remove",
        description=(
            f"Remove {label} from your binder?\n\n"
            f"This will remove **{count}** {_pluralize(count, 'card')}. "
            "They will be available for give, market, merge, and spin again."
        ),
        color=0xff6b8b,
    )
    view = BinderConfirmationView(ctx.author.id, "remove", serials)
    view.message = await ctx.reply(
        embed=embed,
        view=view,
        ephemeral=True,
    )


@slash_command(
    name="list",
    group=binder_group,
    autocomplete={
        "member": _member_autocomplete,
        "era": _group_autocomplete,
        "tier": _tier_autocomplete,
    },
    descriptions={
        "member": "Only show binder cards for one member.",
        "era": "Only show binder cards in an era.",
        "tier": "Only show binder cards of one rarity tier.",
    },
)
async def binder_list(
    ctx,
    era: str = None,
    tier: str = None,
    member: str = None,
):
    """View the cards protected in your binder."""
    filter_labels = []
    conditions = []
    params = [ctx.author.id]

    if era is not None and era.strip():
        resolved_era = _resolve_group(era)
        if resolved_era is None:
            await ctx.reply(
                f"I couldn't identify `{era}` as an era.",
                ephemeral=True,
            )
            return
        conditions.append("era=?")
        params.append(resolved_era)
        filter_labels.append(ERAS[resolved_era]["name"])

    if tier is not None and tier.strip():
        tier_name = _resolve_tier(tier)
        if tier_name is None:
            await ctx.reply(
                f"I couldn't identify `{tier}` as a tier.",
                ephemeral=True,
            )
            return
        conditions.append("rarity=?")
        params.append(tier_name)
        filter_labels.append(tier_name)

    if member is not None and member.strip():
        member_code = _normalize_member(member)
        if member_code is None:
            await ctx.reply(
                f"I couldn't find a tripleS member matching `{member}`.",
                ephemeral=True,
            )
            return
        conditions.append("member_code=?")
        params.append(member_code)
        filter_labels.append(S_MEMBERS[member_code]["name"])

    query = '''SELECT serial, member_code, era, rarity, obtained_at
               FROM cards WHERE owner_id=? AND in_binder=1'''
    if conditions:
        query += " AND " + " AND ".join(conditions)

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            cards = cursor.fetchall()
    except sqlite3.Error as error:
        print(f"Database error while loading binder: {error}")
        await ctx.reply(
            "Your binder couldn't be loaded due to a database error.",
            ephemeral=True,
        )
        return

    if not cards:
        if filter_labels:
            await ctx.reply(
                "No binder cards match those filters. Try `/binder list` "
                "without filters.",
                ephemeral=True,
            )
        else:
            await ctx.reply(
                "Your binder is empty. Protect a card with "
                "`/binder add serial:<serial>`.",
                ephemeral=True,
            )
        return

    cards.sort(
        key=lambda card: (
            ERA_ORDER.get(card[2], len(ERA_ORDER)),
            MEMBER_ORDER.get(card[1], len(MEMBER_ORDER)),
            RARITY_ORDER.get(card[3], len(RARITY_ORDER)),
            card[4] or "",
        )
    )
    view = BinderView(cards, ctx.author, filter_labels)
    view.message = await ctx.reply(
        embed=view.get_embed(),
        view=view,
    )


SLASH_COMMANDS["binder"] = binder_group
bot.tree.add_command(binder_group)
