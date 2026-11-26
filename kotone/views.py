import asyncio
import datetime
import sqlite3
import discord
from discord import app_commands
from discord.ui import Button, View
from eras import ERAS
from kotone.client import (
    SLASH_COMMANDS,
    SLASH_COMMAND_ALIASES,
    preferred_discord_display_name,
)
from kotone.config import (
    RARITIES,
    SPIN_BOARD_SIZE,
    SPIN_BOMB_SLOTS,
    SPIN_REWARD_COUNTS,
    S_MEMBERS,
    S_ORDER,
)
from kotone.cooldowns import (
    check_cooldown,
    set_cooldown,
)
from kotone.db import (
    get_db,
)
from kotone.game import (
    generate_card,
    merge_owned_cards,
    start_card_spin,
)
from kotone.images import (
    COLLECTION_IMAGE_FILENAME,
    COLLECTION_MEMBERS_PER_PAGE,
    create_collection_embed_image,
    create_drop_embed,
    create_drop_embed_image,
    get_card_image,
)


async def replace_remaining_drop_message(message, view):
    async with view.refresh_lock:
        if view.message_replaced:
            return

        with get_db() as conn:
            c = conn.cursor()
            available_cards = []
            for card in view.drop_cards:
                c.execute(
                    "SELECT 1 FROM cards WHERE serial=? AND owner_id IS NULL",
                    (card["serial"],),
                )
                if c.fetchone():
                    available_cards.append(card)

        view.drop_cards = available_cards
        view.message_replaced = True
        new_message = None
        if available_cards:
            embed = create_drop_embed(
                "🎉 Remaining Cards! 🎉",
                "Everyone can now claim the remaining cards!",
                available_cards,
            )
            remaining_image = await create_drop_embed_image(available_cards)
            next_view = View(timeout=30)
            next_view.drop_cards = available_cards
            next_view.refresh_lock = asyncio.Lock()
            next_view.message_replaced = False
            next_view.dropper_id = None

            for index, card in enumerate(available_cards, 1):
                next_view.add_item(
                    ClaimButton(
                        label=f"Claim Card {index}",
                        card_serial=card["serial"],
                    )
                )

            new_message = await message.channel.send(
                embed=embed,
                file=remaining_image,
                view=next_view,
            )

        await message.delete()
        original_message = getattr(view, "original_drop_message", None)
        if original_message is not None:
            await original_message.delete()
            view.original_drop_message = None

        return new_message

# Button for card claiming with race condition protection
class ClaimButton(Button):
    def __init__(self, label, card_serial, style=discord.ButtonStyle.primary):
        super().__init__(label=label, style=style)
        self.card_serial = card_serial
    
    async def callback(self, interaction):
        user_id = interaction.user.id

        dropper_id = getattr(self.view, "dropper_id", None)
        if dropper_id is not None and not self.view.dropper_claimed and user_id != dropper_id:
            await interaction.response.send_message(
                "Only the person who started this drop can claim first.",
                ephemeral=True
            )
            return
        
        # Check claim cooldown
        is_on_cooldown, remaining = check_cooldown(user_id, 'claim', 300)
        if is_on_cooldown:
            await interaction.response.send_message(
                f"You're on cooldown! Please wait {remaining} seconds before claiming another card.",
                ephemeral=True
            )
            return

        await interaction.response.defer()
        
        claim_completed = False
        card_details = None
        try:
            # Use database transaction with exclusive lock to prevent race conditions
            with get_db() as conn:
                c = conn.cursor()
                
                # Start exclusive transaction
                c.execute("BEGIN EXCLUSIVE")
                
                # Check if card is still available (owner_id is NULL)
                c.execute('''SELECT owner_id FROM cards 
                            WHERE serial=? AND owner_id IS NULL''', 
                         (self.card_serial,))
                card = c.fetchone()
                
                if card is not None:
                    # Card is available, claim it
                    c.execute('''UPDATE cards 
                                SET owner_id=?, obtained_at=?, in_binder=0
                                WHERE serial=? AND owner_id IS NULL''',
                             (user_id, str(datetime.datetime.now()), self.card_serial))
                    
                    if c.rowcount > 0:
                        # Successfully claimed
                        c.execute('''SELECT member_code, era, rarity 
                                    FROM cards WHERE serial=?''', 
                                 (self.card_serial,))
                        card_details = c.fetchone()
                        claimant_username = (
                            getattr(interaction.user, "name", None)
                            or str(interaction.user)
                        ).strip()
                        claimant_display_name = preferred_discord_display_name(
                            interaction.user
                        )
                        c.execute(
                            '''INSERT INTO users (user_id, username, display_name)
                               VALUES (?, ?, ?)
                               ON CONFLICT(user_id) DO UPDATE SET
                                   username = excluded.username,
                                   display_name = CASE
                                       WHEN COALESCE(users.custom_display_name, 0) = 0
                                       THEN excluded.display_name
                                       ELSE users.display_name
                                   END
                               WHERE users.username IS NULL
                                  OR users.username != excluded.username
                                  OR (COALESCE(users.custom_display_name, 0) = 0
                                      AND (users.display_name IS NULL
                                           OR users.display_name != excluded.display_name))''',
                            (user_id, claimant_username, claimant_display_name),
                        )
                        
                        # Commit the transaction
                        conn.commit()
                        claim_completed = True

            if not claim_completed:
                # Card was already claimed
                await interaction.followup.send(
                    "This card has already been claimed!", 
                    ephemeral=True
                )
                return

            # Set claim cooldown outside the exclusive card transaction
            set_cooldown(user_id, 'claim', 300)

            member_code, era, rarity = card_details
            claimed_card = {
                "serial": self.card_serial,
                "member_code": member_code,
                "era": era,
                "rarity": rarity,
                "name": ERAS[era]["members"][member_code]["name"],
                "full_name": ERAS[era]["members"][member_code]["full_name"],
            }
            claimed_embed = create_drop_embed(
                "🎉 Card Claimed!",
                f"{interaction.user.mention} claimed **{rarity} "
                f"{claimed_card['name']}** ({self.card_serial}).",
                [claimed_card],
                show_full_name=True,
            )
            claimed_embed.set_image(
                url=get_card_image(
                    era,
                    member_code,
                    rarity,
                    animated=True,
                )
            )
            await interaction.followup.send(
                embed=claimed_embed,
            )
            
            self.disabled = True
            if dropper_id == user_id:
                self.view.dropper_claimed = True
                self.view.stop()
            for child in self.view.children:
                if dropper_id == user_id:
                    child.disabled = True
            if dropper_id is None:
                await replace_remaining_drop_message(
                    interaction.message,
                    self.view,
                )
            
            return
                
        except sqlite3.Error as e:
            print(f"Database error during claim: {e}")
            await interaction.followup.send(
                "An error occurred while claiming the card. Please try again.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error during claim: {e}")
            await interaction.followup.send(
                (
                    "Your card was claimed, but the drop display could not be updated."
                    if claim_completed
                    else "An error occurred while claiming the card. Please try again."
                ),
                ephemeral=True
            )


class SpinChoiceButton(Button):
    def __init__(self, position):
        super().__init__(
            label="?",
            style=discord.ButtonStyle.secondary,
            row=position // 4,
        )
        self.slot_index = position

    async def callback(self, interaction):
        await self.view.choose(interaction, self.slot_index)


class SpinView(View):
    def __init__(self, ctx, wagered_card, outcomes, spins_remaining):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.wagered_card = wagered_card
        self.outcomes = outcomes
        self.spins_remaining = spins_remaining
        self.resolved = False
        self.lock = asyncio.Lock()
        self.message = None

        for position in range(SPIN_BOARD_SIZE):
            self.add_item(SpinChoiceButton(position))

    def get_embed(self, state="pending"):
        if state == "pending":
            reward_counts = SPIN_REWARD_COUNTS[self.wagered_card["rarity"]]
            rarity_odds = " • ".join(
                f"{rarity}: {reward_counts[rarity]}/{SPIN_BOARD_SIZE}"
                for rarity in RARITIES
            )
            description = (
                f"Wagered: **{self.wagered_card['rarity']} "
                f"{self.wagered_card['name']}** "
                f"(`{self.wagered_card['serial']}`) — consumed\n"
                f"Choose one hidden button. An explosion wins nothing; otherwise, "
                f"you get a new card matching the revealed rarity.\n"
                f"This board expires in 3 minutes; the wager is already consumed.\n"
                f"💥 Explosion: {SPIN_BOMB_SLOTS}/{SPIN_BOARD_SIZE}\n"
                f"{rarity_odds}\n"
                f"Spins remaining today: **{self.spins_remaining}**"
            )
            title = "🎰 Card Spin"
        else:
            description = (
                "The cards are spinning... Will you win a new card, "
                "or hit an explosion? ✨"
            )
            title = "🎰 The spin is in motion..."
        return discord.Embed(title=title, description=description, color=0xff6b8b)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Only the person who started this spin can choose a button.",
                ephemeral=True,
            )
            return False
        return True

    async def choose(self, interaction, position):
        await interaction.response.defer()
        async with self.lock:
            if self.resolved:
                await interaction.followup.send(
                    "This spin has already ended.", ephemeral=True
                )
                return
            self.resolved = True
            result = self.outcomes[position]
            reward_card = None

            if result is not None:
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("BEGIN IMMEDIATE")
                        reward_card = generate_card(
                            forced_rarity=result,
                            connection=conn,
                        )
                        cursor.execute(
                            '''INSERT INTO cards
                               (serial, member_code, era, rarity, owner_id, obtained_at)
                               VALUES (?, ?, ?, ?, ?, ?)''',
                            (
                                reward_card["serial"],
                                reward_card["member_code"],
                                reward_card["era"],
                                reward_card["rarity"],
                                self.ctx.author.id,
                                str(datetime.datetime.now()),
                            ),
                        )
                except sqlite3.Error as error:
                    self.resolved = False
                    print(f"Database error while awarding spin card: {error}")
                    await interaction.followup.send(
                        "Your spin reward couldn't be saved. Please choose a button again.",
                        ephemeral=True,
                    )
                    return
                except RuntimeError as error:
                    self.resolved = False
                    print(f"Could not generate spin reward: {error}")
                    await interaction.followup.send(
                        "Your spin reward couldn't be generated. Please choose a button again.",
                        ephemeral=True,
                    )
                    return

            for button in self.children:
                button.disabled = True
            selected_button = self.children[position]
            selected_button.label = "..."
            await interaction.message.edit(
                embed=self.get_embed("spinning"),
                view=self,
            )
            await asyncio.sleep(2)
            if result is None:
                result_embed = discord.Embed(
                    title="💥 Oh no! Your spin exploded!",
                    description=(
                        "That was the unlucky spot! Your wagered card "
                        f"(`{self.wagered_card['serial']}`) is gone, "
                        "and you didn't win a new card. Better luck next time!"
                    ),
                    color=0xff6b8b,
                )
            else:
                result_embed = create_drop_embed(
                    "🎉 Card Spin Successful!",
                    (
                        f"{self.ctx.author.mention} won a **{result} "
                        f"{reward_card['name']}** ({reward_card['serial']})!\n"
                        f"Wagered card `{self.wagered_card['serial']}` was consumed."
                    ),
                    [reward_card],
                    show_full_name=True,
                )
                result_embed.set_image(
                    url=get_card_image(
                        reward_card["era"],
                        reward_card["member_code"],
                        reward_card["rarity"],
                        animated=True,
                    )
                )
            for index, button in enumerate(self.children):
                outcome = self.outcomes[index]
                button.label = "💥" if outcome is None else outcome
                button.style = discord.ButtonStyle.secondary
            selected_button.style = (
                discord.ButtonStyle.danger
                if result is None
                else discord.ButtonStyle.success
            )
            await interaction.message.edit(embed=result_embed, view=self)

    async def on_timeout(self):
        async with self.lock:
            if self.resolved:
                return
            self.resolved = True
            for button in self.children:
                button.disabled = True
            if self.message is not None:
                embed = self.get_embed()
                embed.description += (
                    "\n\n⌛ Spin expired. The wagered card was consumed."
                )
                await self.message.edit(embed=embed, view=self)


class SpinConfirmationView(View):
    def __init__(self, ctx, wagered_card, spins_remaining):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.wagered_card = wagered_card
        self.spins_remaining = spins_remaining
        self.resolved = False
        self.lock = asyncio.Lock()
        self.message = None

    def get_embed(self):
        rarity = self.wagered_card["rarity"]
        reward_counts = SPIN_REWARD_COUNTS[rarity]
        odds = "\n".join(
            f"**{reward_rarity}:** {count}/{SPIN_BOARD_SIZE} "
            f"({count / SPIN_BOARD_SIZE * 100:g}%)"
            for reward_rarity, count in reward_counts.items()
        )
        explosion_chance = SPIN_BOMB_SLOTS / SPIN_BOARD_SIZE * 100
        embed = discord.Embed(
            title="Confirm Card Spin",
            description=(
                f"Are you sure you want to spin "
                f"**{rarity} {self.wagered_card['name']}** "
                f"(`{self.wagered_card['serial']}`)?\n"
                "Confirming permanently consumes this card, even if you hit "
                "the explosion or the spin board expires.\n\n"
                f"**Reward chances for a {rarity} wager:**\n{odds}\n"
                f"**Explosion (no reward):** "
                f"{SPIN_BOMB_SLOTS}/{SPIN_BOARD_SIZE} ({explosion_chance:g}%)\n\n"
                f"You'll have 3 minutes to choose from the 4×4 board. "
                f"Spins remaining today after this: **{self.spins_remaining}**."
            ),
            color=0xff6b8b,
        )
        embed.set_thumbnail(
            url=get_card_image(
                self.wagered_card["era"],
                self.wagered_card["member_code"],
                rarity,
            )
        )
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Only the person who started this spin can confirm it.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Confirm Spin", style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction, button):
        await interaction.response.defer()
        async with self.lock:
            if self.resolved:
                await interaction.followup.send(
                    "This spin confirmation has already ended.",
                    ephemeral=True,
                )
                return
            self.resolved = True
            await interaction.message.edit(
                content="Preparing your spin... ✨",
                embed=None,
                view=None,
            )
            await asyncio.sleep(1.5)
            try:
                wagered_card, outcomes, spins_remaining = start_card_spin(
                    self.ctx.author.id,
                    self.wagered_card["serial"],
                )
            except ValueError as error:
                await interaction.followup.send(str(error))
                self.stop()
                return
            except sqlite3.Error as error:
                print(f"Database error while confirming spin: {error}")
                await interaction.followup.send(
                    "The spin couldn't be started due to a database error. "
                    "Your card was not consumed."
                )
                self.stop()
                return
            except (KeyError, RuntimeError) as error:
                print(f"Could not start confirmed spin: {error}")
                await interaction.followup.send(
                    "The spin couldn't be started. Your card was not consumed."
                )
                self.stop()
                return

            spin_view = SpinView(
                self.ctx,
                wagered_card,
                outcomes,
                spins_remaining,
            )
            spin_view.message = await interaction.message.edit(
                content=None,
                embed=spin_view.get_embed(),
                view=spin_view,
            )
            self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction, button):
        await interaction.response.defer()
        async with self.lock:
            if self.resolved:
                await interaction.followup.send(
                    "This spin confirmation has already ended.",
                    ephemeral=True,
                )
                return
            self.resolved = True
            await interaction.message.edit(
                content="Spin cancelled. Your card was not consumed.",
                embed=None,
                view=None,
            )
            self.stop()

    async def on_timeout(self):
        if self.resolved:
            return
        self.resolved = True
        for button in self.children:
            button.disabled = True
        if self.message is not None:
            await self.message.edit(
                content="Spin confirmation expired. Your card was not consumed.",
                embed=None,
                view=self,
            )


class InventoryView(View):
    def __init__(
        self,
        cards,
        user_display_name,
        ctx,
        selected_member_codes=None,
        filter_labels=None,
    ):
        super().__init__(timeout=180)  # 3 minute timeout
        self.cards = cards
        self.user_display_name = user_display_name
        self.ctx = ctx
        self.selected_member_codes = set(selected_member_codes or ())
        self.filter_labels = filter_labels or []
        self.current_page = 0
        self.items_per_page = 5
        member_select = InventoryMemberSelect(self)
        if member_select.options:
            self.add_item(member_select)
        self.update_buttons()

    def get_filtered_cards(self):
        if not self.selected_member_codes:
            return self.cards
        return [
            card for card in self.cards
            if card[1] in self.selected_member_codes
        ]

    def update_buttons(self):
        filtered_cards = self.get_filtered_cards()
        self.total_pages = max(
            1,
            (len(filtered_cards) + self.items_per_page - 1)
            // self.items_per_page,
        )
        for child in self.children:
            if isinstance(child, Button) and child.label == "◀ Previous":
                child.disabled = self.current_page == 0
            elif isinstance(child, Button) and child.label == "Next ▶":
                child.disabled = self.current_page >= self.total_pages - 1

    def get_embed(self):
        filtered_cards = self.get_filtered_cards()
        filter_labels = list(self.filter_labels)
        if self.selected_member_codes:
            member_names = [
                S_MEMBERS[member_code]["name"]
                for member_code in S_ORDER
                if member_code in self.selected_member_codes
            ]
            filter_labels.append("members " + ", ".join(member_names))
        filter_description = (
            " • Filters: " + ", ".join(filter_labels)
            if filter_labels
            else ""
        )
        embed = discord.Embed(
            title=f"{self.user_display_name}'s Inventory",
            description=(
                f"Page {self.current_page + 1}/{self.total_pages} • "
                f"Total Cards: {len(filtered_cards)}{filter_description}"
            ),
            color=0xff6b8b
        )
        inventory_owner = self.ctx.author
        if self.ctx.message.mentions:
            inventory_owner = self.ctx.message.mentions[0]
        embed.set_author(
            name=self.user_display_name,
            icon_url=inventory_owner.display_avatar.url,
        )
        
        start_idx = self.current_page * self.items_per_page
        end_idx = min(
            (self.current_page + 1) * self.items_per_page,
            len(filtered_cards),
        )
        
        for i in range(start_idx, end_idx):
            serial, member_code, era, rarity, obtained_at, in_binder = (
                filtered_cards[i]
            )
            
            try:
                member_name = ERAS[era]['members'][member_code]['name']
                era_name = ERAS[era]['name']
            except KeyError:
                member_name = "Unknown"
                era_name = "Unknown"
            
            embed.add_field(
                name=f"{'📌 ' if in_binder else ''}{serial}",
                value=(
                    f"Member: {member_name}\nEra: {era_name}\n"
                    f"Rarity: {rarity}\n"
                    f"Binder: {'Protected' if in_binder else 'No'}\n"
                    f"Obtained: {obtained_at[:10] if obtained_at else 'Unknown'}"
                ),
                inline=False
            )

        if not filtered_cards:
            embed.add_field(
                name="No matching cards",
                value="You don't have cards matching the selected filters.",
                inline=False,
            )

        return embed
    
    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This is not your inventory!", ephemeral=True)
            return
        
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This is not your inventory!", ephemeral=True)
            return
        
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)


class InventoryMemberSelect(discord.ui.Select):
    def __init__(self, inventory_view):
        self.inventory_view = inventory_view
        selected_codes = inventory_view.selected_member_codes
        options = [
            discord.SelectOption(
                label=member_data["name"],
                value=member_code,
                default=member_code in selected_codes,
            )
            for member_code, member_data in S_MEMBERS.items()
        ]
        super().__init__(
            placeholder="Filter by one or more members",
            min_values=0,
            max_values=len(options),
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.inventory_view.ctx.author.id:
            await interaction.response.send_message(
                "Only the person who opened this inventory can change its filters.",
                ephemeral=True,
            )
            return

        self.inventory_view.selected_member_codes = set(self.values)
        for option in self.options:
            option.default = option.value in self.inventory_view.selected_member_codes
        self.inventory_view.current_page = 0
        self.inventory_view.update_buttons()
        await interaction.response.edit_message(
            embed=self.inventory_view.get_embed(),
            view=self.inventory_view,
        )


class MergeConfirmationView(View):
    def __init__(self, user_id, serials):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.serials = serials
        self.message = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the person who started this merge can confirm it.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            await self.message.edit(
                content="Merge confirmation expired. No cards were changed.",
                embed=None,
                view=self,
            )

    @discord.ui.button(label="Confirm Merge", style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction, button):
        await interaction.response.edit_message(
            content="Merging...",
            embed=None,
            view=None,
        )
        await asyncio.sleep(3)
        try:
            merged_card = merge_owned_cards(self.user_id, self.serials)
        except ValueError as error:
            await interaction.followup.send(str(error))
            self.stop()
            return
        except sqlite3.Error as error:
            print(f"Database error during card merge: {error}")
            await interaction.followup.send(
                "The merge couldn't be completed due to a database error."
            )
            self.stop()
            return
        except RuntimeError as error:
            print(f"Card merge failed: {error}")
            await interaction.followup.send(
                "The merge couldn't be completed. Please try again."
            )
            self.stop()
            return

        rarity = merged_card["rarity"]
        era = merged_card["era"]
        member_code = merged_card["member_code"]
        result_embed = create_drop_embed(
            "🎉 Card Merged!",
            (
                f"Congratulations, {interaction.user.mention}! You earned "
                f"**{rarity} {merged_card['name']}** "
                f"({merged_card['serial']})."
            ),
            [merged_card],
            show_full_name=True,
        )
        result_embed.set_image(
            url=get_card_image(
                era,
                member_code,
                rarity,
                animated=True,
            )
        )
        await interaction.followup.send(embed=result_embed)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction, button):
        await interaction.response.edit_message(
            content="Merge cancelled. No cards were changed.",
            embed=None,
            view=None,
        )
        self.stop()


def create_collection_embed(
    user,
    era,
    rarity,
    owned_count,
    total_count,
    page=1,
    total_pages=1,
    spare_count=0,
):
    embed = discord.Embed(
        description=(
            f"**{user.name}'s {ERAS[era]['name']} ({rarity}) Collection**"
        ),
        color=0xff6b8b,
    )
    embed.set_author(
        name="Collection",
        icon_url=user.display_avatar.url,
    )
    page_status = (
        f"Page {page}/{total_pages} • "
        if total_pages > 1
        else ""
    )
    embed.description = (
        f"{page_status}{owned_count}/{total_count} Cards\n\n"
        f"**{user.name}'s {ERAS[era]['name']} ({rarity}) Collection:**"
    )
    if owned_count == total_count:
        footer = "Yay, you have collected all cards!"
    else:
        footer = (
            f"You are missing {total_count - owned_count} cards. "
            "Keep playing!"
        )
    if spare_count:
        embed.add_field(
            name="Duplicates",
            value=(
                f"You have **{spare_count} spare {rarity} "
                f"{'card' if spare_count == 1 else 'cards'}**. "
                f"Use `/dupes era:{era} rarity:{rarity}` to view their "
                "serials."
            ),
            inline=False,
        )
    embed.set_footer(text=footer)
    embed.set_image(url=f"attachment://{COLLECTION_IMAGE_FILENAME}")
    return embed

class CollectionRarityButton(Button):
    def __init__(self, rarity, selected=False):
        super().__init__(
            label=rarity,
            style=(
                discord.ButtonStyle.success
                if selected
                else discord.ButtonStyle.secondary
            ),
        )
        self.rarity = rarity

    async def callback(self, interaction):
        await self.view.show_rarity(interaction, self.rarity)


class CollectionPageButton(Button):
    def __init__(self, label, page_delta):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            row=1,
        )
        self.page_delta = page_delta

    async def callback(self, interaction):
        await self.view.show_page(
            interaction,
            self.view.current_page + self.page_delta,
        )


class CollectionView(View):
    def __init__(
        self,
        user,
        era,
        owned_by_rarity,
        default_rarity,
        spare_by_rarity=None,
    ):
        super().__init__(timeout=180)
        self.user = user
        self.era = era
        self.owned_by_rarity = owned_by_rarity
        self.spare_by_rarity = spare_by_rarity or {}
        self.message = None
        self.selected_rarity = default_rarity
        self.current_page = 0
        self.total_pages = (
            (
                len(ERAS[era]["members"])
                + COLLECTION_MEMBERS_PER_PAGE
                - 1
            ) // COLLECTION_MEMBERS_PER_PAGE
            if era in {"ASSEMBLE24", "VV"}
            else 1
        )
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        for rarity in RARITIES:
            self.add_item(
                CollectionRarityButton(
                    rarity,
                    selected=rarity == self.selected_rarity,
                )
            )
        if self.total_pages > 1:
            previous_button = CollectionPageButton("◀ Previous", -1)
            previous_button.disabled = self.current_page == 0
            self.add_item(previous_button)

            next_button = CollectionPageButton("Next ▶", 1)
            next_button.disabled = self.current_page >= self.total_pages - 1
            self.add_item(next_button)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "Only the person who opened this collection can change its rarity.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            await self.message.edit(view=self)

    async def show_rarity(self, interaction, rarity):
        self.selected_rarity = rarity
        await self.update_collection(interaction)

    async def show_page(self, interaction, page):
        if not 0 <= page < self.total_pages:
            await interaction.response.defer()
            return
        self.current_page = page
        await self.update_collection(interaction)

    async def update_collection(self, interaction):
        await interaction.response.defer()
        try:
            owned_codes = self.owned_by_rarity[self.selected_rarity]
            image = await create_collection_embed_image(
                self.era,
                self.selected_rarity,
                owned_codes,
                self.current_page,
            )
            embed = create_collection_embed(
                self.user,
                self.era,
                self.selected_rarity,
                len(owned_codes),
                len(ERAS[self.era]["members"]),
                self.current_page + 1,
                self.total_pages,
                self.spare_by_rarity.get(self.selected_rarity, 0),
            )
            self.update_buttons()
            await interaction.edit_original_response(
                embed=embed,
                attachments=[image],
                view=self,
            )
        except Exception as error:
            print(f"Error while updating collection rarity: {error}")
            await interaction.followup.send(
                "An error occurred while updating your collection.",
                ephemeral=True,
            )


HELP_CATEGORIES = (
    ("💰 Economy", ("daily", "weekly", "balance", "shop", "items", "use", "transfer")),
    (
        "🎴 Cards",
        (
            "drop", "spin", "inventory", "view", "train", "perform", "hunt",
            "merge", "collection", "dupes", "binder", "give", "target", "bias",
            "bio", "profile", "stats", "leaderboard",
        ),
    ),
    ("🏪 Market", ("market", "list", "unlist", "buy")),
    (
        "🎮 Fun & utility",
        (
            "help", "cooldown", "remind", "afk", "minigame", "trivia",
            "8ball", "choose", "rob", "setname",
        ),
    ),
)


class HelpView(View):
    def __init__(self, ctx):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page == len(HELP_CATEGORIES) - 1

    def get_embed(self):
        category_name, command_names = HELP_CATEGORIES[self.current_page]
        command_list = []
        for command_name in command_names:
            command = SLASH_COMMANDS.get(command_name)
            if command is None:
                continue
            description = command.description or "No description available."
            if isinstance(command, app_commands.Group):
                command_list.extend(
                    f"`/{command.name} {subcommand.name}` — "
                    f"{subcommand.description or description}"
                    for subcommand in command.commands
                )
            else:
                aliases = SLASH_COMMAND_ALIASES.get(command.name, ())
                alias_text = (
                    f" (aliases: {', '.join(f'/{alias}' for alias in aliases)})"
                    if aliases
                    else ""
                )
                command_list.append(
                    f"`/{command.name}`{alias_text} — {description}"
                )

        embed = discord.Embed(
            title=f"🦭 Commands • {category_name}",
            description="Use `/help` with a command name to view its details.",
            color=0xff6b8b,
        )
        embed.add_field(
            name="Available commands",
            value="\n".join(command_list) or "No commands available.",
            inline=False,
        )
        embed.set_footer(
            text=f"Page {self.current_page + 1}/{len(HELP_CATEGORIES)}"
        )
        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "This is not your help menu!", ephemeral=True
            )
            return
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "This is not your help menu!", ephemeral=True
            )
            return
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
