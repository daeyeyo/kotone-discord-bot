import datetime
import sqlite3
import discord
from discord.ui import Button, View
from eras import ERAS
from kotone.client import (
    format_fallback_display_name,
    resolve_discord_user_info,
    slash_command,
)
from kotone.db import (
    get_db,
    sync_user_username,
)

@slash_command(
    name='market',
    aliases=('listing', 'mylistings', 'mylisting', 'mymarket'),
)
async def market(ctx):
    """View all market listings, or only your own with /mylistings."""
    own_listings_only = ctx.invoked_with in ('mylistings', 'mylisting', 'mymarket')

    try:
        with get_db() as conn:
            c = conn.cursor()
            query = '''SELECT m.card_serial, m.price, m.seller_id, m.listed_at,
                              c.member_code, c.era, c.rarity
                       FROM market_listings m
                       JOIN cards c ON m.card_serial = c.serial'''
            if own_listings_only:
                query += " WHERE m.seller_id=?"
            query += " ORDER BY m.listed_at DESC"
            params = (ctx.author.id,) if own_listings_only else ()
            c.execute(query, params)
            listings = c.fetchall()

        if not listings:
            if own_listings_only:
                await ctx.reply("You don't have any cards listed on the market.")
                return
            await ctx.reply("The market is empty. List a card with `/list`!")
            return

        seller_ids = {row[2] for row in listings if row[2] is not None}
        stored_seller_names = {}
        if seller_ids:
            placeholders = ",".join("?" for _ in seller_ids)
            with get_db() as conn:
                c = conn.cursor()
                c.execute(
                    f"SELECT user_id, username, display_name FROM users WHERE user_id IN ({placeholders})",
                    tuple(seller_ids),
                )
                stored_seller_names = {
                    row[0]: (row[1], row[2])
                    for row in c.fetchall()
                }

        seller_names = {}
        fetch_budget = [10]
        for seller_id in sorted(seller_ids):
            stored_username, stored_display_name = stored_seller_names.get(
                seller_id,
                (None, None),
            )
            display_name, fetched_names, _ = await resolve_discord_user_info(
                ctx.bot,
                seller_id,
                guild=ctx.guild,
                stored_display_name=stored_display_name,
                stored_username=stored_username,
                fetch_budget=fetch_budget,
            )
            seller_names[seller_id] = discord.utils.escape_markdown(display_name)
            if fetched_names is not None:
                fetched_display, fetched_username = fetched_names
                sync_user_username(
                    seller_id,
                    username=fetched_username,
                    display_name=fetched_display,
                )

        # Create paginated view (reuse InventoryView-like structure)
        # We'll make a simple view with page buttons
        class MarketView(View):
            def __init__(self, listings, ctx, seller_names):
                super().__init__(timeout=120)
                self.listings = listings
                self.ctx = ctx
                self.seller_names = seller_names
                self.current_page = 0
                self.items_per_page = 5
                self.total_pages = (len(listings) + self.items_per_page - 1) // self.items_per_page
                self.update_buttons()

            def update_buttons(self):
                self.children[0].disabled = self.current_page == 0
                self.children[1].disabled = self.current_page >= self.total_pages - 1

            def get_embed(self):
                embed = discord.Embed(
                    title=(
                        "🏪 Your Market Listings"
                        if self.ctx.invoked_with in ('mylistings', 'mylisting', 'mymarket')
                        else "🏪 Market Listings"
                    ),
                    description=f"Page {self.current_page + 1}/{self.total_pages} • Total: {len(self.listings)} cards",
                    color=0x00ff00
                )
                start = self.current_page * self.items_per_page
                end = min(start + self.items_per_page, len(self.listings))
                for i in range(start, end):
                    serial, price, seller_id, listed_at, member_code, era, rarity = self.listings[i]
                    try:
                        member_name = ERAS[era]['members'][member_code]['name']
                        era_name = ERAS[era]['name']
                    except KeyError:
                        member_name = "Unknown"
                        era_name = "Unknown"
                    seller_name = self.seller_names.get(
                        seller_id,
                        discord.utils.escape_markdown(
                            format_fallback_display_name(seller_id)
                        ),
                    )
                    embed.add_field(
                        name=f"{serial} - {member_name}",
                        value=f"Era: {era_name} • Rarity: {rarity}\nPrice: **{price} COMO** • Seller: {seller_name}",
                        inline=False
                    )
                return embed

            @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.primary)
            async def prev_button(self, interaction: discord.Interaction, button: Button):
                if interaction.user.id != self.ctx.author.id:
                    await interaction.response.send_message("This is not your market view!", ephemeral=True)
                    return
                self.current_page -= 1
                self.update_buttons()
                await interaction.response.edit_message(embed=self.get_embed(), view=self)

            @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
            async def next_button(self, interaction: discord.Interaction, button: Button):
                if interaction.user.id != self.ctx.author.id:
                    await interaction.response.send_message("This is not your market view!", ephemeral=True)
                    return
                self.current_page += 1
                self.update_buttons()
                await interaction.response.edit_message(embed=self.get_embed(), view=self)

        view = MarketView(listings, ctx, seller_names)
        embed = view.get_embed()
        await ctx.reply(embed=embed, view=view)

    except Exception as e:
        print(f"Error in market command: {e}")
        await ctx.reply("An error occurred while fetching the market.")


@slash_command(name='list')
async def list_card(ctx, serial: str, price: int):
    """List a card for sale at a given price (COMO)."""
    if price <= 0:
        await ctx.reply("Price must be a positive integer!")
        return

    user_id = ctx.author.id
    error_message = None

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("BEGIN IMMEDIATE")

            # 1. Verify the card exists and belongs to the user
            c.execute(
                '''SELECT owner_id, in_binder FROM cards WHERE serial=?''',
                (serial,),
            )
            row = c.fetchone()
            if not row:
                error_message = "Card not found!"
            elif row[0] != user_id:
                error_message = "You don't own this card!"
            elif row[1]:
                error_message = (
                    "That card is in your binder. Remove it with "
                    "`/binder remove` before listing it."
                )
            else:
                # 2. Check if already listed
                c.execute('''SELECT 1 FROM market_listings WHERE card_serial=?''', (serial,))
                if c.fetchone():
                    error_message = "This card is already on the market!"
                else:
                    # 3. Insert listing
                    listed_at = str(datetime.datetime.now())
                    c.execute('''INSERT INTO market_listings (card_serial, seller_id, price, listed_at)
                                 VALUES (?, ?, ?, ?)''',
                              (serial, user_id, price, listed_at))
                    conn.commit()

        if error_message is not None:
            await ctx.reply(error_message)
            return

        await ctx.reply(f"✅ Your card **{serial}** has been listed for **{price} COMO**!")

    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            await ctx.reply("The market is busy, please try again in a moment.")
        else:
            raise
    except Exception as e:
        print(f"Error in list command: {e}")
        await ctx.reply("An error occurred while listing the card.")


@slash_command(name='unlist')
async def unlist_card(ctx, serial: str):
    """Remove your card from the market."""
    user_id = ctx.author.id
    error_message = None

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("BEGIN IMMEDIATE")

            # Check listing exists and belongs to user
            c.execute('''SELECT seller_id FROM market_listings WHERE card_serial=?''', (serial,))
            row = c.fetchone()
            if not row:
                error_message = "This card is not listed on the market."
            elif row[0] != user_id:
                error_message = "You didn't list this card!"
            else:
                # Delete listing
                c.execute('''DELETE FROM market_listings WHERE card_serial=?''', (serial,))
                conn.commit()

        if error_message is not None:
            await ctx.reply(error_message)
            return

        await ctx.reply(f"✅ Your listing for **{serial}** has been removed.")

    except Exception as e:
        print(f"Error in unlist command: {e}")
        await ctx.reply("An error occurred while removing the listing.")


@slash_command(name='buy')
async def buy_card(ctx, serial: str):
    """Buy a card from the market using COMO."""
    buyer_id = ctx.author.id
    error_message = None
    seller_id = None
    price = None
    card_data = None

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("BEGIN IMMEDIATE")

            # 1. Get listing details
            c.execute('''SELECT seller_id, price FROM market_listings WHERE card_serial=?''', (serial,))
            listing = c.fetchone()
            if not listing:
                error_message = "This card is not listed for sale."
            else:
                seller_id, price = listing
                if seller_id == buyer_id:
                    error_message = "You already own this card – you can't buy your own listing!"
                else:
                    # 2. Get buyer's balance
                    c.execute("SELECT como FROM users WHERE user_id=?", (buyer_id,))
                    buyer_row = c.fetchone()
                    buyer_balance = buyer_row[0] if buyer_row else 0
                    if buyer_balance < price:
                        error_message = f"Insufficient COMO! You have {buyer_balance}, but the card costs {price}."
                    else:
                        # 3. Get seller's balance
                        c.execute("SELECT como FROM users WHERE user_id=?", (seller_id,))
                        seller_row = c.fetchone()
                        seller_balance = seller_row[0] if seller_row else 0

                        # 4. Verify card still owned by seller (defensive)
                        c.execute(
                            "SELECT owner_id, member_code, era, rarity FROM cards WHERE serial=?",
                            (serial,),
                        )
                        card_owner = c.fetchone()
                        if not card_owner or card_owner[0] != seller_id:
                            c.execute("DELETE FROM market_listings WHERE card_serial=?", (serial,))
                            conn.commit()
                            error_message = "The seller no longer owns this card. Listing removed."
                        else:
                            card_data = card_owner[1:]

                            # 5. Perform transaction
                            new_buyer_balance = buyer_balance - price
                            new_seller_balance = seller_balance + price

                            # Update balances
                            c.execute("UPDATE users SET como=? WHERE user_id=?", (new_buyer_balance, buyer_id))
                            c.execute("UPDATE users SET como=? WHERE user_id=?", (new_seller_balance, seller_id))

                            # Transfer card ownership
                            c.execute('''UPDATE cards
                                         SET owner_id=?, obtained_at=?, in_binder=0
                                         WHERE serial=?''',
                                      (buyer_id, str(datetime.datetime.now()), serial))

                            # Remove listing
                            c.execute("DELETE FROM market_listings WHERE card_serial=?", (serial,))

                            conn.commit()

        if error_message is not None:
            await ctx.reply(error_message)
            return

        # Format card name for response
        try:
            if card_data:
                member_code, era, rarity = card_data
                member_name = ERAS[era]['members'][member_code]['name']
                card_desc = f"{rarity} {member_name}"
            else:
                card_desc = serial
        except KeyError:
            card_desc = serial

        await ctx.reply(
            f"✅ Purchase successful! {ctx.author.mention} bought **{card_desc}** ({serial}) "
            f"for **{price} COMO** from <@{seller_id}>."
        )

    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            await ctx.reply("The market is busy, please try again in a moment.")
        else:
            raise
    except Exception as e:
        print(f"Error in buy command: {e}")
        await ctx.reply("An error occurred while processing the purchase.")
