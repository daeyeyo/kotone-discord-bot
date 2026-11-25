import asyncio
import datetime
import sqlite3
import time
import discord
from discord.ui import Button, View
from eras import (
    ERAS,
    ERA_ALIASES,
    ERA_ALIAS_LOOKUP,
    normalize_era_alias,
)
from kotone.client import (
    resolve_discord_user_info,
    slash_command,
)
from kotone.config import (
    RARITIES,
    SPIN_DAILY_LIMIT,
    SPIN_REWARD_COUNTS,
    S_MEMBERS,
    S_ORDER,
)
from kotone.cooldowns import (
    check_cooldown,
    schedule_cooldown_reminder,
)
from kotone.db import (
    get_db,
    sync_user_username,
)
from kotone.game import (
    MERGE_UPGRADES,
    ensure_card_skill,
    format_target,
    generate_unique_cards,
    get_merge_selection,
    get_user_target,
    parse_biases,
)
from kotone.images import (
    DROP_CARD_IMAGE_FILENAME,
    create_collection_embed_image,
    create_drop_embed,
    create_drop_embed_image,
    get_card_image,
)
from kotone.shop import (
    has_active_drop_booster,
)
from kotone.views import (
    ClaimButton,
    CollectionView,
    InventoryView,
    MergeConfirmationView,
    SpinConfirmationView,
    create_collection_embed,
)
from typing import Literal
from io import BytesIO

@slash_command(name='drop')
async def drop(ctx):
    """Drop 3 random cards for claiming."""
    user_id = ctx.author.id

    # Check drop cooldown
    is_on_cooldown, remaining = check_cooldown(user_id, 'drop', 600)
    if is_on_cooldown:
        await ctx.reply(
            f"You're on cooldown! Please wait {remaining} seconds before using drop again."
        )
        return

    try:
        drop_booster_active = has_active_drop_booster(user_id)
        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT extra_drop_slots FROM user_item_effects WHERE user_id=?",
                (user_id,),
            )
            extra_slot_row = c.fetchone()
        extra_slot_available = bool(extra_slot_row and extra_slot_row[0] > 0)

        # Generate one additional card when an activated extra slot is ready.
        cards = generate_unique_cards(
            4 if extra_slot_available else 3,
            target=get_user_target(user_id),
            rarity_boost=drop_booster_active,
        )

        # Store generated cards, consume a queued slot, and start cooldown atomically.
        with get_db() as conn:
            c = conn.cursor()
            c.execute("BEGIN IMMEDIATE")
            now = time.time()
            c.execute(
                '''SELECT expires_at FROM cooldowns
                   WHERE user_id=? AND cooldown_type='drop' ''',
                (user_id,),
            )
            existing_cooldown = c.fetchone()
            if existing_cooldown and existing_cooldown[0] > now:
                remaining = int(existing_cooldown[0] - now)
                await ctx.reply(
                    f"You're on cooldown! Please wait {remaining} seconds before using drop again."
                )
                return

            c.execute(
                "SELECT extra_drop_slots FROM user_item_effects WHERE user_id=?",
                (user_id,),
            )
            current_slot_row = c.fetchone()
            extra_slot_used = bool(
                current_slot_row
                and current_slot_row[0] > 0
                and extra_slot_available
                and len(cards) == 4
            )
            cards_to_drop = cards if extra_slot_used else cards[:3]
            if extra_slot_used:
                c.execute(
                    '''UPDATE user_item_effects
                       SET extra_drop_slots=extra_drop_slots-1
                       WHERE user_id=? AND extra_drop_slots>0''',
                    (user_id,),
                )
                if c.rowcount != 1:
                    raise RuntimeError("The extra drop slot changed before the drop.")

            for card in cards_to_drop:
                c.execute('''INSERT INTO cards
                            (serial, member_code, era, rarity, owner_id, obtained_at)
                            VALUES (?, ?, ?, ?, NULL, NULL)''',
                          (card['serial'], card['member_code'], card['era'], card['rarity']))
            drop_expires_at = now + 600
            c.execute(
                '''INSERT OR REPLACE INTO cooldowns
                   (user_id, cooldown_type, expires_at) VALUES (?, 'drop', ?)''',
                (user_id, drop_expires_at),
            )
            schedule_cooldown_reminder(
                c,
                user_id,
                'drop',
                drop_expires_at,
            )
        cards = cards_to_drop

        embed = create_drop_embed(
            "🎉 Card Drop! 🎉",
            (
                f"{ctx.author.mention} has 30 seconds to claim one card first."
                + (
                    "\n🍀 Your Drop Luck Booster is active!"
                    if drop_booster_active
                    else ""
                )
            ),
            cards,
        )
        drop_image = await create_drop_embed_image(cards)
        drop_image_data = drop_image.fp.getvalue()

        def create_drop_image_attachment():
            return discord.File(
                BytesIO(drop_image_data),
                filename=DROP_CARD_IMAGE_FILENAME,
            )

        # Create view with buttons for dropper
        view = View(timeout=30)
        view.dropper_id = user_id
        view.dropper_claimed = False
        view.drop_cards = cards
        view.refresh_lock = asyncio.Lock()

        for i, card in enumerate(cards, 1):
            button = ClaimButton(label=f"Claim Card {i}", card_serial=card['serial'])
            view.add_item(button)

        # Send message with buttons
        drop_msg = await ctx.send(embed=embed, file=drop_image, view=view)

        async def update_countdown():
            nonlocal drop_msg
            for seconds_remaining in range(25, -1, -5):
                await asyncio.sleep(5)
                if view.is_finished():
                    return
                async with view.refresh_lock:
                    countdown_embed = drop_msg.embeds[0].copy()
                    countdown_embed.set_image(
                        url=f"attachment://{DROP_CARD_IMAGE_FILENAME}"
                    )
                    countdown_embed.description = (
                        f"{ctx.author.mention} has {seconds_remaining} seconds left to claim one card first."
                    )
                    drop_msg = await drop_msg.edit(
                        embed=countdown_embed,
                        attachments=[create_drop_image_attachment()],
                        view=view,
                    )

        countdown_task = asyncio.create_task(update_countdown())
        await view.wait()
        countdown_task.cancel()

        for child in view.children:
            child.disabled = True
        if view.dropper_claimed:
            await drop_msg.delete()
        else:
            description = "The first-claim window expired. The remaining cards are open to everyone."
            async with view.refresh_lock:
                embed = drop_msg.embeds[0].copy()
                embed.set_image(url=f"attachment://{DROP_CARD_IMAGE_FILENAME}")
                embed.description = description
                drop_msg = await drop_msg.edit(
                    embed=embed,
                    attachments=[create_drop_image_attachment()],
                    view=view,
                )

        # Check which cards are still available
        with get_db() as conn:
            c = conn.cursor()
            available_cards = []

            for card in cards:
                c.execute('''SELECT owner_id FROM cards WHERE serial=?''',
                         (card['serial'],))
                result = c.fetchone()

                if result and result[0] is None:
                    available_cards.append(card)

        if available_cards:
            embed2 = create_drop_embed(
                "🎉 Remaining Cards! 🎉",
                "Everyone can now claim the remaining cards!",
                available_cards,
            )
            remaining_image = await create_drop_embed_image(available_cards)

            # Create view with buttons for everyone
            public_view = View(timeout=30)
            public_view.drop_cards = available_cards
            public_view.refresh_lock = asyncio.Lock()
            public_view.message_replaced = False
            public_view.dropper_id = None
            public_view.original_drop_message = (
                None if view.dropper_claimed else drop_msg
            )

            for index, card in enumerate(available_cards, 1):
                button = ClaimButton(
                    label=f"Claim Card {index}",
                    card_serial=card['serial']
                )
                public_view.add_item(button)

            public_msg = await ctx.send(
                embed=embed2,
                file=remaining_image,
                view=public_view,
            )

            # Wait for the public claim period
            await public_view.wait()

            # Disable all buttons after timeout
            for child in public_view.children:
                child.disabled = True

            if not public_view.message_replaced:
                await public_msg.edit(view=public_view)

        await ctx.send("Card drop event has ended!")

    except Exception as e:
        print(f"Error in drop command: {e}")
        await ctx.reply("An error occurred while dropping cards. Please try again.")


@slash_command(name='spin')
async def spin(ctx, serial: str = ""):
    """Preview the odds and confirm wagering an owned card on a spin.

    Confirming consumes the wager. Each spin has one explosion among 16 buttons,
    and up to five spins are allowed per local day.
    """
    serial = serial.strip()
    if not serial:
        await ctx.reply(
            "Choose one of your owned card serials with `/spin serial`. "
            "Your wagered card is consumed."
        )
        return
    if len(serial) > 50:
        await ctx.reply("Invalid serial number.")
        return

    today = datetime.date.today().isoformat()
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''SELECT member_code, era, rarity, in_binder
                   FROM cards WHERE serial=? AND owner_id=?''',
                (serial, ctx.author.id),
            )
            card_row = cursor.fetchone()
            if card_row is None:
                await ctx.reply("You don't own a card with that serial.")
                return
            member_code, era, rarity, in_binder = card_row
            if in_binder:
                await ctx.reply(
                    "That card is in your binder. Remove it with "
                    "`/binder remove` before spinning."
                )
                return
            if rarity not in SPIN_REWARD_COUNTS:
                await ctx.reply(
                    "That card has an unsupported rarity and can't be spun."
                )
                return
            cursor.execute(
                "SELECT 1 FROM market_listings WHERE card_serial=?",
                (serial,),
            )
            if cursor.fetchone():
                await ctx.reply(
                    "Unlist that card from the market before using it for a spin."
                )
                return
            cursor.execute(
                "SELECT spin_date, spins FROM spin_usage WHERE user_id=?",
                (ctx.author.id,),
            )
            usage_row = cursor.fetchone()
            spins_used = (
                usage_row[1]
                if usage_row and usage_row[0] == today
                else 0
            )
            if spins_used >= SPIN_DAILY_LIMIT:
                await ctx.reply(
                    f"You've used all **{SPIN_DAILY_LIMIT} spins** for today. "
                    "Your limit resets at local midnight."
                )
                return
            member = ERAS[era]["members"][member_code]
            wagered_card = {
                "serial": serial,
                "member_code": member_code,
                "era": era,
                "rarity": rarity,
                "name": member["name"],
                "full_name": member["full_name"],
            }
    except sqlite3.Error as error:
        print(f"Database error while preparing spin for {ctx.author.id}: {error}")
        await ctx.reply("Spin odds couldn't be checked due to a database error.")
        return
    except KeyError as error:
        print(f"Could not prepare spin for {ctx.author.id}: {error}")
        await ctx.reply("That card's details couldn't be loaded for a spin.")
        return

    view = SpinConfirmationView(
        ctx,
        wagered_card,
        SPIN_DAILY_LIMIT - spins_used - 1,
    )
    view.message = await ctx.reply(
        embed=view.get_embed(),
        view=view,
    )


@slash_command(name='merge')
async def merge_cards(ctx, *, card_serials: str = ""):
    """Confirm a merge of selected owned cards into the next rarity."""
    serials = card_serials.replace(",", " ").split()
    if len(serials) not in {9, 10} or len(set(serials)) != len(serials):
        await ctx.reply(
            "Provide 10 different serials, or 9 after activating a Merge Discount Token. Example: "
            "`/merge` with the card serials separated by spaces."
        )
        return

    try:
        with get_db() as conn:
            selected_rarity, selected_cards = get_merge_selection(
                conn.cursor(),
                ctx.author.id,
                serials,
            )
    except ValueError as error:
        await ctx.reply(str(error))
        return
    except sqlite3.Error as error:
        print(f"Database error while checking merge cards: {error}")
        await ctx.reply("The merge couldn't be started due to a database error.")
        return

    next_rarity = MERGE_UPGRADES[selected_rarity]
    serial_count = len(serials)
    token_note = (
        " Your activated Merge Discount Token will be consumed."
        if serial_count == 9
        else ""
    )
    confirmation_embed = discord.Embed(
        title="Confirm Card Merge",
        description=(
            f"Merge these {serial_count} **{selected_rarity}** cards into 1 random "
            f"**{next_rarity}** card? This will permanently consume the cards below."
            f"{token_note}"
        ),
        color=0xff6b8b,
    )
    card_list = []
    for serial, member_code, era, rarity, _, _ in selected_cards:
        member_name = ERAS[era]["members"][member_code]["full_name"]
        card_list.append(
            f"• `{serial}` — {member_name} ({ERAS[era]['name']}, {rarity})"
        )
    confirmation_embed.add_field(
        name="Cards to consume",
        value="\n".join(card_list),
        inline=False,
    )

    view = MergeConfirmationView(ctx.author.id, serials)
    view.message = await ctx.reply(embed=confirmation_embed, view=view)


@slash_command(name='collection')
async def collection(
    ctx,
    era: Literal["AAA", "ASSEMBLE", "ASSEMBLE24", "KRE", "VV"],
    rarity: Literal["Common", "Rare", "Epic", "Legendary", "Mythic"] = "Common",
):
    """Show your owned cards for one era, with rarity filters."""
    era_name = era.strip()
    era = ERA_ALIAS_LOOKUP.get(normalize_era_alias(era_name))
    if era is None or era not in ERAS:
        available_eras = ", ".join(
            f"{ERAS[era_key]['name']} ({aliases[1]})"
            for era_key, aliases in ERA_ALIASES.items()
        )
        await ctx.reply(
            f"I couldn't identify `{era_name}` as an era. "
            f"Available eras: {available_eras}."
        )
        return

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                '''SELECT member_code, rarity FROM cards
                   WHERE owner_id=? AND era=?''',
                (ctx.author.id, era),
            )
            owned_by_rarity = {name: set() for name in RARITIES}
            copies_by_rarity = {name: {} for name in RARITIES}
            for member_code, card_rarity in c.fetchall():
                if card_rarity in owned_by_rarity:
                    owned_by_rarity[card_rarity].add(member_code)
                    rarity_counts = copies_by_rarity[card_rarity]
                    rarity_counts[member_code] = (
                        rarity_counts.get(member_code, 0) + 1
                    )

        spare_by_rarity = {
            rarity_name: sum(
                count - 1
                for count in member_counts.values()
                if count > 1
            )
            for rarity_name, member_counts in copies_by_rarity.items()
        }
        view = CollectionView(
            ctx.author,
            era,
            owned_by_rarity,
            rarity,
            spare_by_rarity,
        )
        embed = create_collection_embed(
            ctx.author,
            era,
            rarity,
            len(owned_by_rarity[rarity]),
            len(ERAS[era]["members"]),
            1,
            view.total_pages,
            spare_by_rarity.get(rarity, 0),
        )
        image = await create_collection_embed_image(
            era,
            rarity,
            owned_by_rarity[rarity],
        )
        view.message = await ctx.reply(
            embed=embed,
            file=image,
            view=view,
        )
    except sqlite3.Error as error:
        print(f"Database error while loading collection: {error}")
        await ctx.reply("An error occurred while loading your collection.")
    except Exception as error:
        print(f"Error while creating collection: {error}")
        await ctx.reply("An error occurred while creating your collection.")


DUPLICATE_GROUPS_PER_PAGE = 10
DUPLICATE_COPIES_PER_FIELD = 15
DUPLICATE_SERIALS_PER_FIELD = 50


def get_duplicate_group_names(group):
    era_data = ERAS.get(group["era"], {})
    era_name = era_data.get("name", group["era"])
    member_name = (
        era_data.get("members", {})
        .get(group["member_code"], {})
        .get("name", group["member_code"])
    )
    return era_name, member_name


def get_duplicate_group_key(group):
    return f"{group['era']}|{group['member_code']}|{group['rarity']}"


def count_ready_spares(group):
    return max(
        0,
        group["copies"] - group["listed"] - group["binder"] - 1,
    )


def pluralize(count, singular, plural=None):
    if count == 1:
        return singular
    return plural or f"{singular}s"


def fetch_duplicate_groups(user_id, era=None, rarity=None, member_codes=None):
    query = '''
        SELECT c.era, c.member_code, c.rarity,
               COUNT(*) AS copies,
               SUM(CASE WHEN m.card_serial IS NOT NULL THEN 1 ELSE 0 END)
                   AS listed,
               SUM(CASE WHEN c.in_binder=1 THEN 1 ELSE 0 END) AS binder
        FROM cards c
        LEFT JOIN market_listings m ON m.card_serial = c.serial
        WHERE c.owner_id = ?
    '''
    params = [user_id]

    if era is not None:
        query += " AND c.era = ?"
        params.append(era)
    if rarity is not None:
        query += " AND c.rarity = ?"
        params.append(rarity)
    if member_codes:
        placeholders = ", ".join("?" for _ in member_codes)
        query += f" AND c.member_code IN ({placeholders})"
        params.extend(sorted(member_codes))

    query += '''
        GROUP BY c.era, c.member_code, c.rarity
        HAVING COUNT(*) > 1
    '''

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        groups = [
            {
                "era": group_era,
                "member_code": member_code,
                "rarity": group_rarity,
                "copies": copies,
                "listed": listed or 0,
                "binder": binder or 0,
            }
            for (
                group_era,
                member_code,
                group_rarity,
                copies,
                listed,
                binder,
            ) in cursor.fetchall()
        ]

    era_order = {era_key: index for index, era_key in enumerate(ERAS)}
    member_order = {
        member_code: index for index, member_code in enumerate(S_ORDER)
    }
    rarity_order = {
        rarity_name: index for index, rarity_name in enumerate(RARITIES)
    }
    groups.sort(
        key=lambda group: (
            era_order.get(group["era"], len(era_order)),
            member_order.get(
                group["member_code"],
                len(member_order),
            ),
            rarity_order.get(group["rarity"], len(rarity_order)),
        )
    )
    return groups


def fetch_duplicate_copies(user_id, group):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT c.serial, c.obtained_at, m.price, c.in_binder
               FROM cards c
               LEFT JOIN market_listings m
                   ON m.card_serial = c.serial
               WHERE c.owner_id=? AND c.era=?
                   AND c.member_code=? AND c.rarity=?
               ORDER BY c.in_binder,
                        (m.card_serial IS NOT NULL),
                        c.obtained_at IS NULL,
                        c.obtained_at,
                        c.id''',
            (
                user_id,
                group["era"],
                group["member_code"],
                group["rarity"],
            ),
        )
        return cursor.fetchall()


class DuplicateGroupSelect(discord.ui.Select):
    def __init__(self, view):
        self.duplicate_view = view
        options = []
        for group in view.page_groups():
            era_name, member_name = get_duplicate_group_names(group)
            spare_count = group["copies"] - 1
            available_count = count_ready_spares(group)
            details = [
                f"{spare_count} {pluralize(spare_count, 'spare')}"
            ]
            if group["listed"] or group["binder"]:
                details.append(f"{available_count} ready")
            if group["listed"]:
                details.append(f"{group['listed']} listed")
            if group["binder"]:
                details.append(f"{group['binder']} in binder")
            options.append(
                discord.SelectOption(
                    label=(
                        f"{member_name} • {group['rarity']} "
                        f"(×{group['copies']})"
                    )[:100],
                    value=get_duplicate_group_key(group),
                    description=(
                        f"{era_name} • " + " • ".join(details)
                    )[:100],
                )
            )
        super().__init__(
            placeholder="Choose a duplicate group to see spare serials",
            options=options,
            row=0,
        )

    async def callback(self, interaction):
        group = self.duplicate_view.get_group_by_key(self.values[0])
        if group is None:
            await interaction.response.send_message(
                "That duplicate group is no longer on this page. "
                "Please reopen `/dupes`.",
                ephemeral=True,
            )
            return
        await self.duplicate_view.show_group_serials(interaction, group)


class DuplicateView(View):
    def __init__(self, user, groups, filter_labels=None):
        super().__init__(timeout=180)
        self.user = user
        self.groups = groups
        self.filter_labels = filter_labels or []
        self.page = 0
        self.message = None
        self.update_items()

    @property
    def total_pages(self):
        return max(
            1,
            (len(self.groups) + DUPLICATE_GROUPS_PER_PAGE - 1)
            // DUPLICATE_GROUPS_PER_PAGE,
        )

    def page_groups(self):
        start = self.page * DUPLICATE_GROUPS_PER_PAGE
        return self.groups[start:start + DUPLICATE_GROUPS_PER_PAGE]

    def get_group_by_key(self, key):
        return next(
            (
                group
                for group in self.page_groups()
                if get_duplicate_group_key(group) == key
            ),
            None,
        )

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "Only the person who opened this duplicate list can use it.",
                ephemeral=True,
            )
            return False
        return True

    def update_items(self):
        self.clear_items()
        self.add_item(DuplicateGroupSelect(self))
        if self.total_pages > 1:
            previous_button = Button(
                label="◀ Previous",
                style=discord.ButtonStyle.primary,
                row=1,
                disabled=self.page == 0,
            )
            previous_button.callback = self.show_previous_page
            self.add_item(previous_button)

            next_button = Button(
                label="Next ▶",
                style=discord.ButtonStyle.primary,
                row=1,
                disabled=self.page >= self.total_pages - 1,
            )
            next_button.callback = self.show_next_page
            self.add_item(next_button)

    async def show_previous_page(self, interaction):
        self.page = max(0, self.page - 1)
        self.update_items()
        await interaction.response.edit_message(
            embed=self.get_embed(),
            view=self,
        )

    async def show_next_page(self, interaction):
        self.page = min(self.total_pages - 1, self.page + 1)
        self.update_items()
        await interaction.response.edit_message(
            embed=self.get_embed(),
            view=self,
        )

    def get_embed(self):
        spare_total = sum(group["copies"] - 1 for group in self.groups)
        ready_total = sum(count_ready_spares(group) for group in self.groups)
        listed_total = sum(group["listed"] for group in self.groups)
        binder_total = sum(group["binder"] for group in self.groups)

        description_parts = [
            (
                f"**{len(self.groups)} duplicate "
                f"{pluralize(len(self.groups), 'group')}**"
            ),
            (
                f"**{spare_total} "
                f"{pluralize(spare_total, 'spare card')}**"
            ),
        ]
        if ready_total:
            description_parts.append(f"**{ready_total} ready to use**")
        if listed_total:
            description_parts.append(f"{listed_total} listed")
        if binder_total:
            description_parts.append(f"{binder_total} in binder")

        description = " • ".join(description_parts) + (
            "\nPick a group to see exact serials. The oldest available copy "
            "is the keeper; every other copy is a spare."
        )
        if self.filter_labels:
            description += "\nFilters: " + " • ".join(self.filter_labels)

        embed = discord.Embed(
            title=f"{self.user.display_name}'s Duplicates",
            description=description,
            color=0xff6b8b,
        )
        embed.set_author(
            name="Duplicate tracker",
            icon_url=self.user.display_avatar.url,
        )

        for group in self.page_groups():
            era_name, member_name = get_duplicate_group_names(group)
            spare_count = group["copies"] - 1
            details = [
                f"{spare_count} {pluralize(spare_count, 'spare')}"
            ]
            if group["listed"] or group["binder"]:
                details.append(
                    f"{count_ready_spares(group)} ready to use"
                )
            if group["listed"]:
                details.append(f"{group['listed']} listed")
            if group["binder"]:
                details.append(f"{group['binder']} in binder")
            embed.add_field(
                name=(
                    f"{era_name} • {member_name} • {group['rarity']} "
                    f"— ×{group['copies']}"
                ),
                value=" • ".join(details),
                inline=False,
            )

        embed.set_footer(
            text=(
                f"Page {self.page + 1}/{self.total_pages} • "
                "Use `/dupes` filters to narrow this list"
            )
        )
        return embed

    async def show_group_serials(self, interaction, group):
        try:
            rows = fetch_duplicate_copies(self.user.id, group)
        except sqlite3.Error as error:
            print(f"Database error while loading duplicate serials: {error}")
            await interaction.response.send_message(
                "I couldn't load that duplicate group. Please try again.",
                ephemeral=True,
            )
            return

        if len(rows) < 2:
            await interaction.response.send_message(
                "That group no longer has duplicates. "
                "Reopen `/dupes` to refresh.",
                ephemeral=True,
            )
            return

        era_name, member_name = get_duplicate_group_names(group)
        keeper_serial, _, keeper_price, keeper_bound = rows[0]
        binder_rows = [row for row in rows if row[3]]
        listed_serials = [
            (serial, price)
            for serial, _, price, bound in rows[1:]
            if price is not None and not bound
        ]
        ready_serials = [
            serial
            for serial, _, price, bound in rows[1:]
            if price is None and not bound
        ]

        spare_count = len(rows) - 1
        description = (
            f"You own **{len(rows)} copies** — "
            f"**{spare_count} {pluralize(spare_count, 'spare')}**.\n"
            f"Keeper: `{keeper_serial}`"
        )
        if keeper_bound:
            description += " (in binder)"
        if keeper_price is not None:
            description += f" (listed for **{keeper_price:,} COMO**)"
        if binder_rows:
            description += (
                f"\n**{len(binder_rows)} "
                f"{pluralize(len(binder_rows), 'copy', 'copies')}** "
                "protected in your binder."
            )
        if not ready_serials:
            description += (
                "\nNo unprotected, unlisted spares are currently available. "
                "Use `/unlist` or `/binder remove` to free one up."
            )

        embed = discord.Embed(
            title=f"{era_name} • {member_name} • {group['rarity']}",
            description=description,
            color=0xff6b8b,
        )
        embed.set_author(
            name="Duplicate serials",
            icon_url=self.user.display_avatar.url,
        )

        copy_lines = []
        for index, (serial, _, price, bound) in enumerate(rows):
            if index == 0:
                status = "keeper"
            elif bound:
                status = "spare • protected in binder"
            elif price is None:
                status = "spare • ready to use"
            else:
                status = f"spare • listed for {price:,} COMO"
            if index == 0 and bound:
                status += " • protected in binder"
            if index == 0 and price is not None:
                status += f" • listed for {price:,} COMO"
            copy_lines.append(f"`{serial}` — {status}")

        shown_copies = copy_lines[:DUPLICATE_COPIES_PER_FIELD]
        embed.add_field(
            name="Copies",
            value="\n".join(shown_copies),
            inline=False,
        )
        if len(copy_lines) > len(shown_copies):
            embed.add_field(
                name="More copies",
                value=(
                    f"+{len(copy_lines) - len(shown_copies)} more copies "
                    "not shown."
                ),
                inline=False,
            )

        if ready_serials:
            shown_serials = ready_serials[:DUPLICATE_SERIALS_PER_FIELD]
            embed.add_field(
                name=f"Ready-to-use spares ({len(ready_serials)})",
                value=" ".join(f"`{serial}`" for serial in shown_serials),
                inline=False,
            )
            embed.add_field(
                name="Copy for /merge",
                value=f"```{' '.join(shown_serials)}```",
                inline=False,
            )
            if len(ready_serials) > len(shown_serials):
                embed.add_field(
                    name="More spares",
                    value=(
                        f"{len(ready_serials) - len(shown_serials)} more "
                        "ready-to-use spares are not shown. Use `/inventory` "
                        "or narrow the filters."
                    ),
                    inline=False,
                )

        if binder_rows:
            binder_lines = [
                f"`{serial}` — protected"
                for serial, _, _, _
                in binder_rows[:DUPLICATE_COPIES_PER_FIELD]
            ]
            embed.add_field(
                name=f"Binder copies ({len(binder_rows)})",
                value="\n".join(binder_lines),
                inline=False,
            )
            if len(binder_rows) > len(binder_lines):
                embed.add_field(
                    name="More binder copies",
                    value=(
                        f"+{len(binder_rows) - len(binder_lines)} more "
                        "protected copies not shown."
                    ),
                    inline=False,
                )

        if listed_serials:
            listed_lines = [
                f"`{serial}` — {price:,} COMO"
                for serial, price
                in listed_serials[:DUPLICATE_COPIES_PER_FIELD]
            ]
            embed.add_field(
                name=f"Listed spares ({len(listed_serials)})",
                value="\n".join(listed_lines),
                inline=False,
            )
            if len(listed_serials) > len(listed_lines):
                embed.add_field(
                    name="More listed spares",
                    value=(
                        f"+{len(listed_serials) - len(listed_lines)} more "
                        "listed copies not shown."
                    ),
                    inline=False,
                )

        embed.add_field(
            name="Use a spare with",
            value=(
                "`/spin serial:<serial>`\n"
                "`/list serial:<serial> price:<amount>`\n"
                "`/give recipient:@user serial:<serial>`\n"
                "`/merge` — paste the copy-for-merge line\n"
                "`/binder remove serial:<serial>` — free a protected copy"
            ),
            inline=False,
        )
        embed.set_footer(
            text=(
                "Keeper prefers the oldest unprotected, unlisted copy. "
                "Binder copies are never included as ready spares."
            )
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


@slash_command(name='dupes', aliases=('duplicates', 'dupe'))
async def duplicates(
    ctx,
    era: Literal["AAA", "ASSEMBLE", "ASSEMBLE24", "KRE", "VV"] = None,
    rarity: Literal["Common", "Rare", "Epic", "Legendary", "Mythic"] = None,
    member: str = None,
):
    """Find duplicate cards and copy spare serials for merging, spinning, or trading."""
    if era is not None:
        era_name = era.strip()
        resolved_era = ERA_ALIAS_LOOKUP.get(normalize_era_alias(era_name))
        if resolved_era is None or resolved_era not in ERAS:
            await ctx.reply(
                f"I couldn't identify `{era_name}` as an era."
            )
            return
        era = resolved_era

    if rarity is not None and rarity not in RARITIES:
        await ctx.reply(f"I couldn't identify `{rarity}` as a rarity.")
        return

    member_codes = None
    if member:
        normalized_member = " ".join(member.casefold().split())
        member_codes = {
            member_code
            for member_code, member_data in S_MEMBERS.items()
            if normalized_member in {
                member_code.casefold(),
                " ".join(member_data["name"].casefold().split()),
                " ".join(member_data["full_name"].casefold().split()),
            }
        }
        if not member_codes:
            await ctx.reply(
                f"I couldn't find a tripleS member matching `{member}`."
            )
            return

    filter_labels = []
    if era:
        filter_labels.append(ERAS[era]["name"])
    if rarity:
        filter_labels.append(rarity)
    if member_codes:
        filter_labels.append(
            "Member: "
            + ", ".join(
                S_MEMBERS[member_code]["name"]
                for member_code in S_ORDER
                if member_code in member_codes
            )
        )

    try:
        groups = fetch_duplicate_groups(
            ctx.author.id,
            era=era,
            rarity=rarity,
            member_codes=member_codes,
        )
    except sqlite3.Error as error:
        print(f"Database error while loading duplicates: {error}")
        await ctx.reply("An error occurred while loading your duplicates.")
        return

    if not groups:
        if filter_labels:
            await ctx.reply(
                "No duplicates match those filters. Try `/dupes` without "
                "filters to see every duplicate group."
            )
        else:
            await ctx.reply(
                "You don't have any duplicate cards yet. Duplicates are "
                "copies with the same member, era, and rarity."
            )
        return

    view = DuplicateView(ctx.author, groups, filter_labels)
    view.message = await ctx.reply(embed=view.get_embed(), view=view)


@slash_command(name='inventory', aliases=('inv',))
async def inventory(
    ctx,
    user: discord.Member = None,
    era: Literal["AAA", "ASSEMBLE", "ASSEMBLE24", "KRE", "VV"] = None,
    rarity: Literal["Common", "Rare", "Epic", "Legendary", "Mythic"] = None,
    member: Literal[
        "Seoyeon", "Hyerin", "Jiwoo", "Chaeyeon", "Yooyeon", "Soomin",
        "Nakyoung", "Yubin", "Kaede", "Dahyun", "Kotone", "Yeonji",
        "Nien", "Sohyun", "Xinyu", "Mayu", "Lynn", "Joobin", "Hayeon",
        "Shion", "Chaewon", "Sullin", "Seoah", "Jiyeon",
    ] = None,
):
    """View cards, or filter by era, rarity, and one or more members."""
    user = user or ctx.author
    member_codes = {
        member_code
        for member_code, member_data in S_MEMBERS.items()
        if member
        and member_data["name"].casefold() == member.casefold()
    }
    filter_labels = []
    if era:
        filter_labels.append(f"era {era}")
    if rarity:
        filter_labels.append(f"rarity {rarity}")
    user_id = user.id

    try:
        with get_db() as conn:
            c = conn.cursor()

            # Get user's cards
            c.execute('''SELECT serial, member_code, era, rarity, obtained_at,
                                in_binder
                         FROM cards
                         WHERE owner_id=?
                         ORDER BY in_binder DESC, obtained_at DESC''', (user_id,))
            cards = [
                card
                for card in c.fetchall()
                if (era is None or card[2] == era)
                and (rarity is None or card[3] == rarity)
            ]

        if not cards and not (era or rarity or member):
            await ctx.reply(f"{user.display_name} doesn't have any cards yet!")
            return

        # Create paginated view
        view = InventoryView(
            cards,
            user.display_name,
            ctx,
            selected_member_codes=member_codes,
            filter_labels=filter_labels,
        )
        embed = view.get_embed()

        await ctx.reply(embed=embed, view=view)

    except Exception as e:
        print(f"Error in inventory command: {e}")
        await ctx.reply("An error occurred while fetching inventory. Please try again.")


@slash_command(name='view')
async def view_card(ctx, serial: str):
    """View detailed information about a specific card."""
    # Basic input validation
    if len(serial) > 50:
        await ctx.reply("Invalid serial number!")
        return

    try:
        with get_db() as conn:
            c = conn.cursor()

            # Get card details
            c.execute('''SELECT member_code, era, rarity, owner_id, obtained_at
                         FROM cards
                         WHERE serial=?''', (serial,))

            card = c.fetchone()

        if not card:
            await ctx.reply("Card not found!")
            return

        member_code, era, rarity, owner_id, obtained_at = card

        with get_db() as conn:
            c = conn.cursor()
            skills = ensure_card_skill(c, serial, member_code, rarity)

        # Get owner username and display_name
        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT username, display_name FROM users WHERE user_id=?",
                (owner_id,),
            )
            owner = c.fetchone()

        stored_owner_name = owner[0] if owner else None
        stored_owner_display_name = owner[1] if owner else None
        if owner_id:
            owner_name, fetched_names, owner_user = await resolve_discord_user_info(
                ctx.bot,
                owner_id,
                guild=ctx.guild,
                stored_display_name=stored_owner_display_name,
                stored_username=stored_owner_name,
            )
            if fetched_names is not None:
                fetched_display, fetched_username = fetched_names
                sync_user_username(
                    owner_id,
                    username=fetched_username,
                    display_name=fetched_display,
                )
        else:
            owner_name = "Unclaimed"
            owner_user = None

        # Get card info
        try:
            full_name = ERAS[era]['members'][member_code]['full_name']
            era_name = ERAS[era]['name']
            image_url = get_card_image(
                era,
                member_code,
                rarity,
                animated=True,
            )
        except KeyError:
            await ctx.reply("Card data corrupted!")
            return

        # Create embed
        embed = discord.Embed(
            description=f"**{full_name}**",
            color=0xff6b8b
        )
        embed.set_author(
            name=serial,
            icon_url=owner_user.display_avatar.url if owner_user else None,
        )

        # Set the card image
        embed.set_image(url=image_url)

        embed.add_field(name="Rarity", value=rarity, inline=True)
        embed.add_field(name="Era", value=era_name, inline=True)
        embed.add_field(
            name="Owner",
            value=discord.utils.escape_markdown(owner_name),
            inline=True,
        )
        embed.add_field(
            name="Obtained",
            value=obtained_at[:10] if obtained_at else "Unknown",
            inline=True
        )
        embed.add_field(
            name="Skill",
            value=f"**{skills['skill']}**",
            inline=True,
        )
        embed.add_field(
            name="Skill Points",
            value=f"**{skills['points']}** / {skills['cap']}",
            inline=True,
        )
        embed.add_field(
            name="Training Sessions",
            value=f"**{skills['training_sessions']}**",
            inline=True,
        )
        embed.add_field(
            name="Performances",
            value=f"**{skills['performances']}**",
            inline=True,
        )

        # Set color based on rarity
        rarity_colors = {
            "Common": 0x808080,     # Gray
            "Rare": 0x0070FF,       # Blue
            "Epic": 0x800080,       # Purple
            "Legendary": 0xFFD700,  # Gold
            "Mythic": 0xFF4FD8      # Pink
        }
        embed.color = rarity_colors.get(rarity, 0xff6b8b)

        await ctx.reply(embed=embed)

    except Exception as e:
        print(f"Error in view command: {e}")
        await ctx.reply("An error occurred while viewing the card. Please try again.")


@slash_command(name='give', aliases=('gift', 'send'))
async def give_card(ctx, recipient: discord.Member, serial: str):
    """Give a card to another user."""
    # Validation
    if ctx.author.id == recipient.id:
        await ctx.reply("You can't give a card to yourself!")
        return

    if len(serial) > 50:
        await ctx.reply("Invalid serial number!")
        return

    if recipient.bot:
        await ctx.reply("You can't give cards to bots!")
        return

    try:
        with get_db() as conn:
            c = conn.cursor()

            # Check if the card exists and belongs to the sender
            c.execute('''SELECT owner_id, member_code, era, rarity, in_binder
                        FROM cards WHERE serial=?''', (serial,))
            card = c.fetchone()

            if not card:
                await ctx.reply("Card not found!")
                return

            if card[0] != ctx.author.id:
                await ctx.reply("You don't own this card!")
                return

            if card[4]:
                await ctx.reply(
                    "That card is in your binder. Remove it with "
                    "`/binder remove` before giving it away."
                )
                return

            # Check if recipient exists in users table, if not create them
            c.execute("SELECT user_id FROM users WHERE user_id=?", (recipient.id,))
            recipient_exists = c.fetchone()

            if not recipient_exists:
                c.execute('''INSERT INTO users (user_id, username)
                            VALUES (?, ?)''',
                          (recipient.id, str(recipient)))

            # Transfer the card
            c.execute('''UPDATE cards
                        SET owner_id=?, obtained_at=?, in_binder=0
                        WHERE serial=?''',
                      (recipient.id, str(datetime.datetime.now()), serial))

        # Get card details for message
        member_code, era, rarity = card[1], card[2], card[3]
        try:
            member_name = ERAS[era]['members'][member_code]['name']
            card_desc = f"{rarity} {member_name}"
        except KeyError:
            card_desc = serial

        await ctx.reply(
            f"{ctx.author.mention} has given **{card_desc}** ({serial}) to {recipient.mention}!"
        )

    except Exception as e:
        print(f"Error in give command: {e}")
        await ctx.reply("An error occurred while transferring the card. Please try again.")


@slash_command(name='target')
async def target_command(
    ctx,
    member: Literal[
        "Seoyeon", "Hyerin", "Jiwoo", "Chaeyeon", "Yooyeon", "Soomin",
        "Nakyoung", "Yubin", "Kaede", "Dahyun", "Kotone", "Yeonji",
        "Nien", "Sohyun", "Xinyu", "Mayu", "Lynn", "Joobin", "Hayeon",
        "Shion", "Chaewon", "Sullin", "Seoah", "Jiyeon",
    ] = None,
    rarity: Literal["Common", "Rare", "Epic", "Legendary", "Mythic"] = None,
    era: Literal["AAA", "ASSEMBLE", "ASSEMBLE24", "KRE", "VV"] = None,
    clear: bool = False,
):
    """Set a member target with optional rarity/era filters, or clear it."""
    member_query = " ".join(member.casefold().split()) if member else ""
    if clear:
        if member_query or rarity or era:
            await ctx.reply(
                "Use `clear` by itself, or provide a member and optional filters to set a target."
            )
            return
        with get_db() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM user_targets WHERE user_id=?", (ctx.author.id,))
        await ctx.reply("Your card target has been cleared.")
        return

    if not member_query:
        if rarity or era:
            await ctx.reply("Choose a member when setting a rarity or era target.")
            return
        current_target = get_user_target(ctx.author.id)
        if current_target:
            await ctx.reply(
                f"Your current target is **{format_target(current_target)}**. "
                "Set a new member to update it, or enable `clear` to remove it."
            )
        else:
            await ctx.reply(
                "Set a member, with optional rarity and era filters, or enable `clear`."
            )
        return

    matching_members = {
        (era_code, member_code)
        for era_code, era_data in ERAS.items()
        for member_code, member_data in era_data["members"].items()
        if (era is None or era_code == era)
        and member_query in {
            member_code.casefold(),
            member_data["name"].casefold(),
            member_data["full_name"].casefold(),
        }
    }

    member_codes = {member_code for _, member_code in matching_members}
    if not member_query or not member_codes:
        await ctx.reply(
            "I couldn't find that member. Try their short name, full name, or member code."
        )
        return
    if len(member_codes) > 1:
        await ctx.reply(
            "That name matches multiple members. Please use a more specific name or member code."
        )
        return

    member_code = next(iter(member_codes))
    target = {"era": era, "member_code": member_code, "rarity": rarity}
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (ctx.author.id, str(ctx.author)),
        )
        c.execute(
            '''INSERT OR REPLACE INTO user_targets
               (user_id, era, member_code, rarity)
               VALUES (?, ?, ?, ?)''',
            (ctx.author.id, era, member_code, rarity),
        )

    await ctx.reply(
        f"Your card target is now **{format_target(target)}**. "
        "It gets a small +5 percentage-point chance on generated cards."
    )


@slash_command(name='bias')
async def bias_command(ctx, members: str = None, clear: bool = False):
    """Set or clear the members shown as your profile biases."""
    members = members.strip() if members else ""
    if clear:
        if members:
            await ctx.reply("Use `clear` by itself, or provide members to replace your biases.")
            return
        with get_db() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM user_biases WHERE user_id=?", (ctx.author.id,))
        await ctx.reply("Your profile biases have been cleared.")
        return

    if not members:
        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT member_code FROM user_biases WHERE user_id=?",
                (ctx.author.id,),
            )
            current_codes = {row[0] for row in c.fetchall()}
        current_names = [
            S_MEMBERS[code]["name"]
            for code in S_ORDER
            if code in current_codes
        ]
        await ctx.reply(
            f"Your current profile biases: {', '.join(current_names)}."
            if current_names
            else "You haven't set any profile biases yet. Provide member names to set them."
        )
        return

    try:
        bias_codes = parse_biases(members)
    except ValueError as error:
        await ctx.reply(str(error))
        return

    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (ctx.author.id, str(ctx.author)),
        )
        c.execute("DELETE FROM user_biases WHERE user_id=?", (ctx.author.id,))
        c.executemany(
            "INSERT INTO user_biases (user_id, member_code) VALUES (?, ?)",
            ((ctx.author.id, member_code) for member_code in bias_codes),
        )

    display_names = [S_MEMBERS[code]["name"] for code in bias_codes]
    await ctx.reply(
        "Your profile biases have been set! **"
        + ", ".join(display_names)
        + "**"
    )
