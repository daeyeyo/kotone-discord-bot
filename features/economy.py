import asyncio
import datetime
import random
import sqlite3
import time
import discord
from kotone.client import (
    slash_command,
)
from kotone.cooldowns import (
    schedule_cooldown_reminder,
)
from kotone.db import (
    get_db,
)
from kotone.game import (
    generate_card,
    get_user_target,
)
from kotone.shop import (
    SHOP_ITEMS,
    SHOP_ITEM_ALIASES,
    advance_daily_streak,
    purchase_shop_item,
    use_shop_item,
)

@slash_command(name='daily')
async def daily(ctx):
    """Claim your daily COMO reward (24h cooldown)."""
    user_id = ctx.author.id
    username = str(ctx.author)
    today = datetime.datetime.now().date()

    # Retry up to 3 times if database is locked
    daily_card = generate_card(target=get_user_target(user_id))
    for attempt in range(3):
        try:
            reply_message = None
            with get_db() as conn:
                c = conn.cursor()
                # Acquire write lock immediately
                c.execute("BEGIN IMMEDIATE")

                # --- Check cooldown ---
                current_time = time.time()
                c.execute('''SELECT expires_at FROM cooldowns
                             WHERE user_id=? AND cooldown_type=?''',
                          (user_id, 'daily'))
                row = c.fetchone()
                if row:
                    remaining = int(row[0] - current_time)
                    if remaining > 0:
                        # Still on cooldown
                        hours = remaining // 3600
                        minutes = (remaining % 3600) // 60
                        seconds = remaining % 60
                        reply_message = (
                            f"You've already claimed your daily COMO today! "
                            f"You can claim again in **{hours}h {minutes}m {seconds}s**."
                        )
                    else:
                        # Expired cooldown – delete it
                        c.execute('''DELETE FROM cooldowns
                                     WHERE user_id=? AND cooldown_type=?''',
                                  (user_id, 'daily'))

                if reply_message is None:
                    # --- Process daily claim ---
                    # Check if user exists
                    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
                    user = c.fetchone()

                    if user:
                        last_daily = datetime.datetime.strptime(user[3], '%Y-%m-%d').date() if user[3] else None
                        current_streak = user[2]
                        current_como = user[4]
                        new_streak, streak_shield_used = advance_daily_streak(
                            c,
                            user_id,
                            last_daily,
                            today,
                            current_streak,
                        )

                        # Calculate reward
                        base_reward = random.randint(100, 200)
                        if new_streak >= 5:
                            reward = base_reward * 2
                            bonus_msg = " (2x streak bonus applied!)"
                        else:
                            reward = base_reward
                            bonus_msg = ""
                        if streak_shield_used:
                            bonus_msg += " (Streak Shield used!)"

                        new_como = current_como + reward

                        # Update user record
                        c.execute('''UPDATE users
                                     SET username=?, daily_streak=?, last_daily=?, como=?
                                     WHERE user_id=?''',
                                  (username, new_streak, str(today), new_como, user_id))
                    else:
                        # New user
                        reward = random.randint(100, 200)
                        new_streak = 1
                        new_como = reward
                        bonus_msg = ""
                        c.execute('''INSERT INTO users
                                     (user_id, username, daily_streak, last_daily, como)
                                     VALUES (?, ?, ?, ?, ?)''',
                                  (user_id, username, new_streak, str(today), new_como))

                    # Set 24h cooldown
                    c.execute(
                        "INSERT INTO cards (serial, member_code, era, rarity, owner_id, obtained_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (daily_card['serial'], daily_card['member_code'], daily_card['era'], daily_card['rarity'], user_id, str(datetime.datetime.now())),
                    )
                    expires_at = time.time() + 86400
                    c.execute('''INSERT OR REPLACE INTO cooldowns
                                 (user_id, cooldown_type, expires_at)
                                 VALUES (?, ?, ?)''',
                              (user_id, 'daily', expires_at))
                    schedule_cooldown_reminder(
                        c,
                        user_id,
                        'daily',
                        expires_at,
                    )

                    # Commit everything
                    conn.commit()

                    reply_message = (
                        f"You've received **{reward} COMO**!{bonus_msg}\n"
                        f"Daily card: **{daily_card['rarity']} {daily_card['name']}** ({daily_card['serial']})\n"
                        f"Current streak: **{new_streak}** days\n"
                        f"Total COMO: **{new_como}**"
                    )

            await ctx.reply(reply_message)
            return  # Success – exit the retry loop

        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < 2:
                await asyncio.sleep(0.5 * (attempt + 1))  # backoff
                continue
            else:
                # Re-raise if it's not a lock error or we exhausted retries
                raise
        except Exception as e:
            print(f"Error in daily command: {e}")
            await ctx.reply("An error occurred. Please try again later.")
            return


@slash_command(name='balance', aliases=('como', 'bal'))
async def balance(ctx, user: discord.Member = None):
    """Check COMO balance for yourself or another user."""
    user = user or ctx.author
    user_id = user.id

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT como FROM users WHERE user_id=?", (user_id,))
            result = c.fetchone()

        if result:
            como = result[0]
            await ctx.reply(f"{user.display_name} has {como} COMO")
        else:
            if user.id == ctx.author.id:
                await ctx.reply("You don't have a COMO balance yet. Use `/daily` to get started!")
            else:
                await ctx.reply(f"{user.display_name} doesn't have a COMO balance yet.")
    except Exception as e:
        print(f"Error in balance command: {e}")
        await ctx.reply("An error occurred. Please try again later.")


@slash_command(name='shop')
async def shop(ctx, *, query: str = ""):
    """View shop items or purchase an item with COMO."""
    parts = query.strip().split(maxsplit=1)
    if not parts:
        embed = discord.Embed(
            title="🛍️ Kotone Shop",
            description=(
                "Items go into your item inventory. View them with `/items` "
                "and activate them with `/use`."
            ),
            color=0xff6b8b,
        )
        embed.add_field(
            name="🍀 Drop Luck Booster — 600 COMO",
            value=(
                "Boosts Rare, Epic, Legendary, and Mythic drop weights for 1 hour when used. "
                "Using another while active extends its duration.\n"
                "`/shop` with `buy booster`"
            ),
            inline=False,
        )
        embed.add_field(
            name="🎴 Drop Cooldown Reset — 200 COMO",
            value="Use while `/drop` is on cooldown to reset it.\n`/shop` with `buy drop`",
            inline=False,
        )
        embed.add_field(
            name="🔀 Merge Discount Token — 1,200 COMO",
            value=(
                "Activate it to merge 9 same-rarity cards instead of 10. "
                "It is consumed only when the merge is confirmed.\n"
                "`/shop` with `buy merge`, then `/use` with `merge`"
            ),
            inline=False,
        )
        embed.add_field(
            name="🛡️ Streak Shield — 800 COMO",
            value=(
                "Activate it to automatically protect your streak after missing "
                "exactly one day. It is consumed only when needed.\n"
                "`/shop` with `buy shield`, then `/use` with `shield`"
            ),
            inline=False,
        )
        embed.add_field(
            name="🎴 Extra Drop Slot — 400 COMO",
            value=(
                "Activate it to add one card to your next successful `/drop`.\n"
                "`/shop` with `buy extra_drop`, then `/use` with `extra_drop`"
            ),
            inline=False,
        )
        try:
            with get_db() as conn:
                c = conn.cursor()
                c.execute("SELECT como FROM users WHERE user_id=?", (ctx.author.id,))
                balance_row = c.fetchone()
                c.execute(
                    "SELECT expires_at FROM user_drop_boosters WHERE user_id=?",
                    (ctx.author.id,),
                )
                booster_row = c.fetchone()
            balance_amount = balance_row[0] if balance_row else 0
            embed.set_footer(text=f"Your balance: {balance_amount} COMO")
            if booster_row and booster_row[0] > time.time():
                remaining = max(0, int(booster_row[0] - time.time()))
                minutes, seconds = divmod(remaining, 60)
                embed.add_field(
                    name="Active booster",
                    value=f"{minutes}m {seconds}s remaining",
                    inline=False,
                )
            await ctx.reply(embed=embed)
        except sqlite3.Error as error:
            print(f"Database error while viewing shop: {error}")
            await ctx.reply("The shop couldn't be loaded due to a database error.")
        return

    action = parts[0].casefold()
    item_name = parts[1] if len(parts) > 1 else ""
    if action != "buy" or not item_name:
        await ctx.reply(
            "Use `/shop` without an option to view items, or set its query to "
            "`buy <item>` to purchase one."
        )
        return
    item_key = SHOP_ITEM_ALIASES.get(item_name.strip().casefold().replace(" ", "_"))
    if item_key is None:
        await ctx.reply(
            "Unknown shop item. Use `/shop` to see available items."
        )
        return

    try:
        new_balance = purchase_shop_item(ctx.author.id, item_key)
        await ctx.reply(
            f"Bought **{SHOP_ITEMS[item_key]['name']}** for "
            f"**{SHOP_ITEMS[item_key]['price']} COMO**. It's now in `/items`. "
            f"Your balance is **{new_balance} COMO**."
        )
    except ValueError as error:
        await ctx.reply(str(error))
    except sqlite3.Error as error:
        print(f"Database error while purchasing shop item: {error}")
        await ctx.reply("The purchase couldn't be completed due to a database error.")


@slash_command(name='items')
async def items(ctx):
    """Show the items in your consumable inventory."""
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                '''SELECT item_key, quantity FROM user_items
                   WHERE user_id=? AND quantity>0 ORDER BY item_key''',
                (ctx.author.id,),
            )
            inventory = c.fetchall()
            c.execute(
                "SELECT expires_at FROM user_drop_boosters WHERE user_id=?",
                (ctx.author.id,),
            )
            booster = c.fetchone()
            c.execute(
                '''SELECT merge_discounts, streak_shields, extra_drop_slots
                   FROM user_item_effects WHERE user_id=?''',
                (ctx.author.id,),
            )
            active_effects = c.fetchone()

        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Items",
            color=0xff6b8b,
        )
        embed.set_author(
            name=ctx.author.name,
            icon_url=ctx.author.display_avatar.url,
        )
        if inventory:
            for item_key, quantity in inventory:
                item = SHOP_ITEMS.get(item_key)
                if item is not None:
                    embed.add_field(
                        name=item["name"],
                        value=f"Quantity: **{quantity}**\nUse `/use` with `{item_key}`.",
                        inline=False,
                    )
        elif (
            (not active_effects or not any(active_effects))
            and not (booster and booster[0] > time.time())
        ):
            embed.description = "You don't have any items yet. Visit `/shop` to buy some."
        else:
            embed.description = "Your item inventory is empty; activated effects are listed below."

        if booster and booster[0] > time.time():
            remaining = max(0, int(booster[0] - time.time()))
            minutes, seconds = divmod(remaining, 60)
            embed.add_field(
                name="Active Drop Luck Booster",
                value=f"{minutes}m {seconds}s remaining",
                inline=False,
            )
        if active_effects:
            effect_labels = (
                ("Merge Discounts Ready", active_effects[0]),
                ("Streak Shields Armed", active_effects[1]),
                ("Extra Drop Slots Ready", active_effects[2]),
            )
            for label, quantity in effect_labels:
                if quantity:
                    embed.add_field(
                        name=label,
                        value=f"**{quantity}** ready",
                        inline=False,
                    )
        await ctx.reply(embed=embed)
    except sqlite3.Error as error:
        print(f"Database error while viewing items: {error}")
        await ctx.reply("Your items couldn't be loaded due to a database error.")


@slash_command(name='use')
async def use_item(ctx, *, item_name: str = ""):
    """Consume an item from your item inventory."""
    item_key = SHOP_ITEM_ALIASES.get(
        item_name.strip().casefold().replace(" ", "_")
    )
    if item_key is None:
        await ctx.reply(
            "Choose an item to use with `/use`: `booster`, `drop`, "
            "`merge`, `shield`, or `extra_drop`."
        )
        return

    try:
        confirmation = use_shop_item(ctx.author.id, item_key)
        await ctx.reply(f"{confirmation}.")
    except ValueError as error:
        await ctx.reply(str(error))
    except sqlite3.Error as error:
        print(f"Database error while using shop item: {error}")
        await ctx.reply("The item couldn't be used due to a database error.")
    except RuntimeError as error:
        print(f"Shop item use failed: {error}")
        await ctx.reply("The item couldn't be used. Please try again.")


@slash_command(name='weekly')
async def weekly(ctx):
    """Claim your weekly COMO and random card reward (7-day cooldown)."""
    user_id = ctx.author.id
    username = str(ctx.author)
    weekly_card = generate_card(target=get_user_target(user_id))
    cooldown_message = None

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("BEGIN IMMEDIATE")

            c.execute('''SELECT expires_at FROM cooldowns
                         WHERE user_id=? AND cooldown_type=?''',
                      (user_id, 'weekly'))
            cooldown = c.fetchone()
            if cooldown:
                remaining = int(cooldown[0] - time.time())
                if remaining > 0:
                    days = remaining // 86400
                    hours = (remaining % 86400) // 3600
                    cooldown_message = (
                        f"You've already claimed your weekly reward! "
                        f"You can claim again in **{days}d {hours}h**."
                    )
                else:
                    c.execute('''DELETE FROM cooldowns
                                 WHERE user_id=? AND cooldown_type=?''',
                              (user_id, 'weekly'))

            if cooldown_message is None:
                # Get or create user
                c.execute("SELECT como FROM users WHERE user_id=?", (user_id,))
                user = c.fetchone()
                if user:
                    current_como = user[0]
                else:
                    # Create new user with 0 COMO
                    c.execute('''INSERT INTO users (user_id, username, daily_streak, last_daily, como)
                                 VALUES (?, ?, 0, NULL, 0)''',
                              (user_id, username))
                    current_como = 0

                # Reward: 500-1000 COMO (more than daily)
                reward = random.randint(500, 1000)
                new_como = current_como + reward

                # Update balance
                c.execute("UPDATE users SET como=? WHERE user_id=?", (new_como, user_id))

                c.execute(
                    '''INSERT INTO cards
                       (serial, member_code, era, rarity, owner_id, obtained_at)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (
                        weekly_card['serial'],
                        weekly_card['member_code'],
                        weekly_card['era'],
                        weekly_card['rarity'],
                        user_id,
                        str(datetime.datetime.now()),
                    ),
                )

                # Set 7-day cooldown
                expires_at = time.time() + 604800
                c.execute("INSERT OR REPLACE INTO cooldowns (user_id, cooldown_type, expires_at) VALUES (?, ?, ?)", (user_id, 'weekly', expires_at))
                schedule_cooldown_reminder(
                    c,
                    user_id,
                    'weekly',
                    expires_at,
                )

                conn.commit()

        if cooldown_message is not None:
            await ctx.reply(cooldown_message)
            return

        await ctx.reply(
            f"You've received your weekly reward of **{reward} COMO**! "
            f"Total COMO: **{new_como}**\n"
            f"Weekly card: **{weekly_card['rarity']} {weekly_card['name']}** "
            f"({weekly_card['serial']})"
        )

    except Exception as e:
        print(f"Error in weekly command: {e}")
        await ctx.reply("An error occurred. Please try again later.")


@slash_command(name='rob')
async def rob(ctx, user: discord.Member = None):
    """Funny easter egg: no robbing allowed!"""
    responses = [
        "Hey you are not allowed to rob!",
        "No robbing please :(",
        "Don't rob!!",
        "We don't do that here :((",
        "Robbing is illegal! 🚨",
        "You can't steal COMO! Be nice!",
        "I'm calling the police! 👮",
        "Nice try! But no.",
        "That's not how we do things here.",
        "Please don't rob, it's not cool."
    ]
    if user:
        await ctx.reply(f"{random.choice(responses)} (and don't bother {user.display_name} either!)")
    else:
        await ctx.reply(random.choice(responses))


@slash_command(name='transfer')
async def transfer(ctx, recipient: discord.Member, amount: int):
    """Transfer COMO to another user."""
    sender_id = ctx.author.id
    recipient_id = recipient.id

    if sender_id == recipient_id:
        await ctx.reply("You can't transfer COMO to yourself!")
        return

    if amount <= 0:
        await ctx.reply("Amount must be a positive integer!")
        return

    error_message = None

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("BEGIN IMMEDIATE")

            # Get sender's balance
            c.execute("SELECT como FROM users WHERE user_id=?", (sender_id,))
            sender_row = c.fetchone()
            if not sender_row:
                error_message = "You don't have any COMO yet. Use `/daily` to get some!"
            else:
                sender_balance = sender_row[0]
                if sender_balance < amount:
                    error_message = f"You don't have enough COMO! You have {sender_balance}."
                else:
                    # Get recipient's balance (or create if not exists)
                    c.execute("SELECT como FROM users WHERE user_id=?", (recipient_id,))
                    recipient_row = c.fetchone()
                    if recipient_row:
                        recipient_balance = recipient_row[0]
                    else:
                        # Create user with 0 COMO
                        c.execute('''INSERT INTO users (user_id, username, daily_streak, last_daily, como)
                                     VALUES (?, ?, 0, NULL, 0)''',
                                  (recipient_id, str(recipient)))
                        recipient_balance = 0

                    # Update balances
                    new_sender = sender_balance - amount
                    new_recipient = recipient_balance + amount
                    c.execute("UPDATE users SET como=? WHERE user_id=?", (new_sender, sender_id))
                    c.execute("UPDATE users SET como=? WHERE user_id=?", (new_recipient, recipient_id))

                    conn.commit()

        if error_message is not None:
            await ctx.reply(error_message)
            return

        await ctx.reply(f"✅ Successfully transferred **{amount} COMO** to {recipient.mention}!")

    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            await ctx.reply("The system is busy, please try again in a moment.")
        else:
            raise
    except Exception as e:
        print(f"Error in transfer command: {e}")
        await ctx.reply("An error occurred while processing the transfer.")
