import datetime
import random
import sqlite3
import time
import discord
from discord import app_commands
from kotone.client import (
    SLASH_COMMANDS,
    SLASH_COMMAND_ALIASES,
    invalidate_user_name_cache,
    preferred_discord_display_name,
    resolve_discord_user_info,
    slash_command,
)
from kotone.config import (
    MINIGAMES,
    RARITIES,
    SPIN_DAILY_LIMIT,
    S_MEMBERS,
    S_ORDER,
)
from kotone.cooldowns import (
    COOLDOWN_REMINDER_TYPES,
    next_local_midnight_timestamp,
)
from kotone.db import (
    get_db,
    set_guild_afk,
    set_user_display_name,
    sync_user_username,
)
from kotone.game import (
    format_target,
    get_user_target,
)
from kotone.views import (
    HelpView,
)
from typing import Literal

@slash_command(name='8ball')
async def eight_ball(ctx, *, question):
    """Ask the magic 8-ball a question."""
    responses = [
        "It is certain.", "It is decidedly so.", "Without a doubt.",
        "Yes - definitely.", "You may rely on it.", "As I see it, yes.",
        "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
        "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
        "Cannot predict now.", "Concentrate and ask again.", "Don't count on it.",
        "My reply is no.", "My sources say no.", "Outlook not so good.",
        "Very doubtful."
    ]
    await ctx.reply(
        f"({question}) – {random.choice(responses)}",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@slash_command(name='choose')
async def choose(
    ctx,
    option1: str,
    option2: str,
    option3: str = None,
    option4: str = None,
    option5: str = None,
):
    """Choose between two to five options."""
    choices = [
        option.strip()
        for option in (option1, option2, option3, option4, option5)
        if option and option.strip()
    ]
    if len(choices) < 2:
        await ctx.reply("Please provide at least two non-empty options.")
        return

    await ctx.reply(
        f"({' or '.join(choices)}) – {random.choice(choices)}!",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@slash_command(name="minigame")
async def minigame(ctx):
    """Show the available minigames and their commands."""
    embed = discord.Embed(
        title="🎮 Minigames",
        description=(
            "Each minigame has its own command. "
            "Use the command listed with a minigame to play it."
        ),
        color=0xff6b8b,
    )
    for number, (name, description, command) in enumerate(MINIGAMES, 1):
        embed.add_field(
            name=f"{number}. {name}",
            value=f"- {description}\nPlay with `{command}`",
            inline=False,
        )
    if not MINIGAMES:
        embed.description = "No minigames are available yet. Check back later!"
    await ctx.reply(embed=embed)


def _parse_numeric_user_id(raw_value):
    if raw_value is None:
        return None
    cleaned = str(raw_value).strip()
    if cleaned.startswith("<@") and cleaned.endswith(">"):
        cleaned = cleaned[2:-1]
        if cleaned.startswith("!"):
            cleaned = cleaned[1:]
    cleaned = cleaned.strip()
    if not (cleaned.isascii() and cleaned.isdigit()):
        return None
    parsed = int(cleaned)
    if parsed <= 0 or parsed > (1 << 63) - 1:
        return None
    return parsed


@slash_command(
    name='profile',
    descriptions={
        "user": "Server member whose profile to view.",
        "user_id": "Optional numeric player ID (e.g. 900000000000000008).",
    },
)
async def profile(ctx, user: discord.Member = None, user_id: str = None):
    """Show a player's card collection profile."""
    if user is not None:
        target_user = user
        target_id = user.id
    elif user_id is not None:
        target_id = _parse_numeric_user_id(user_id)
        if target_id is None:
            await ctx.reply("Please provide a valid numeric player ID.")
            return
        target_user = None
    else:
        target_user = ctx.author
        target_id = ctx.author.id

    if target_user is not None:
        discord_username = (
            getattr(target_user, "name", None) or str(target_user)
        ).strip()
        discord_display_name = preferred_discord_display_name(target_user)
        sync_user_username(
            target_id,
            username=discord_username,
            display_name=discord_display_name,
        )

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM cards WHERE owner_id=?", (target_id,))
            card_count = c.fetchone()[0]
            c.execute(
                "SELECT como, daily_streak, username, display_name FROM users WHERE user_id=?",
                (target_id,),
            )
            user_row = c.fetchone()
            c.execute(
                "SELECT member_code FROM user_biases WHERE user_id=?",
                (target_id,),
            )
            bias_codes = {row[0] for row in c.fetchall()}
            c.execute(
                "SELECT bio FROM user_bios WHERE user_id=?",
                (target_id,),
            )
            bio_row = c.fetchone()

        stored_username = user_row[2] if user_row else None
        stored_display_name = user_row[3] if user_row else None
        resolved_name, fetched_names, resolved_discord_user = await resolve_discord_user_info(
            ctx.bot,
            target_id,
            guild=ctx.guild,
            stored_display_name=stored_display_name,
            stored_username=stored_username,
        )
        if fetched_names is not None:
            sync_user_username(
                target_id,
                username=fetched_names[1],
                display_name=fetched_names[0],
            )

        target = get_user_target(target_id)
        embed = discord.Embed(
            title=f"{discord.utils.escape_markdown(resolved_name)}'s Profile",
            color=0xff6b8b,
        )
        author_user = target_user or resolved_discord_user
        if author_user is not None:
            embed.set_author(
                name=author_user.name,
                icon_url=author_user.display_avatar.url,
            )
        else:
            embed.set_author(name=f"ID: {target_id}")
        bias_names = ", ".join(
            S_MEMBERS[code]["name"]
            for code in S_ORDER if code in bias_codes
        ) or "None set"
        bio_text = bio_row[0] if bio_row else "No bio set."
        profile_lines = [
            f"📝 **Bio:**\n{bio_text}",
            "",
            "**Info:**",
            f"💰 **Balance:** {(user_row[0] or 0) if user_row else 0}",
            f"🎴 **Cards:** {card_count}",
            f"🔥 **Streak:** {(user_row[1] or 0) if user_row else 0} days",
            f"🎯 **Target:** {format_target(target) if target else 'None set'}",
            f"💖 **Bias:** {bias_names}",
        ]
        embed.description = "\n".join(profile_lines)
        await ctx.reply(embed=embed)
    except Exception as e:
        print(f"Error in profile command: {e}")
        await ctx.reply("An error occurred while fetching the profile.")


@slash_command(
    name='setname',
    descriptions={
        "user_id": "The numeric player ID (e.g. 900000000000000008) to rename.",
        "name": "The display name to save in the database (1-64 characters).",
    },
)
async def setname(ctx, user_id: str, name: str):
    """Admin/owner command to set a player's display name in the database."""
    is_owner = await ctx.bot.is_bot_owner(ctx.author.id)
    is_admin = (
        ctx.guild is not None
        and isinstance(ctx.author, discord.Member)
        and ctx.author.guild_permissions.administrator
    )
    if not (is_owner or is_admin):
        await ctx.reply(
            "Only a bot owner or server administrator can use `/setname`."
        )
        return

    target_id = _parse_numeric_user_id(user_id)
    if target_id is None:
        await ctx.reply(
            "Please provide a valid numeric player ID (for example `900000000000000008`)."
        )
        return

    try:
        saved_name = set_user_display_name(target_id, name)
    except ValueError as error:
        await ctx.reply(str(error))
        return
    except sqlite3.Error as error:
        print(f"Database error in setname command: {error}")
        await ctx.reply("Could not save display name due to a database error.")
        return

    invalidate_user_name_cache(target_id)
    await ctx.reply(
        f"✅ Set display name for `{target_id}` to **{discord.utils.escape_markdown(saved_name)}**.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@slash_command(name='bio')
async def bio_command(
    ctx,
    action: Literal["set", "clear"],
    bio: str = None,
):
    """Set or clear your profile bio."""
    if action == "clear":
        with get_db() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM user_bios WHERE user_id=?", (ctx.author.id,))
        await ctx.reply("Your profile bio has been cleared.")
        return

    if bio is None or not bio.strip():
        await ctx.reply("Provide the bio text when choosing `set`.")
        return

    bio = bio.strip()
    if len(bio) > 300:
        await ctx.reply("Your bio must be 300 characters or fewer.")
        return

    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (ctx.author.id, str(ctx.author)),
        )
        c.execute(
            '''INSERT OR REPLACE INTO user_bios (user_id, bio)
               VALUES (?, ?)''',
            (ctx.author.id, bio),
        )

    await ctx.reply("Your profile bio has been set!")


@slash_command(name='stats')
async def stats(ctx, user: discord.Member = None):
    """View statistics about your card collection."""
    user = user or ctx.author
    user_id = user.id

    rarity_counts = {}
    era_counts = {}
    como = 0
    streak = 0

    try:
        with get_db() as conn:
            c = conn.cursor()

            # Get total cards
            c.execute('''SELECT COUNT(*) FROM cards WHERE owner_id=?''', (user_id,))
            total_cards = c.fetchone()[0]

            if total_cards > 0:
                # Get rarity breakdown
                c.execute('''SELECT rarity, COUNT(*) FROM cards
                            WHERE owner_id=? GROUP BY rarity''', (user_id,))
                rarity_counts = dict(c.fetchall())

                # Get era breakdown
                c.execute('''SELECT era, COUNT(*) FROM cards
                            WHERE owner_id=? GROUP BY era''', (user_id,))
                era_counts = dict(c.fetchall())

                # Get user info
                c.execute('''SELECT como, daily_streak FROM users WHERE user_id=?''', (user_id,))
                user_info = c.fetchone()
                como = user_info[0] if user_info else 0
                streak = user_info[1] if user_info else 0

        if total_cards == 0:
            await ctx.reply(f"{user.display_name} doesn't have any cards yet!")
            return

        # Create embed
        embed = discord.Embed(
            title=f"📊 {user.display_name}'s Stats",
            color=0xff6b8b
        )

        embed.add_field(
            name="💎 Total Cards",
            value=str(total_cards),
            inline=True
        )
        embed.add_field(
            name="💰 COMO",
            value=str(como),
            inline=True
        )
        embed.add_field(
            name="🔥 Daily Streak",
            value=f"{streak} days",
            inline=True
        )

        # Rarity breakdown
        rarity_text = "\n".join([
            f"{rarity}: {rarity_counts.get(rarity, 0)}"
            for rarity in RARITIES
        ])
        embed.add_field(
            name="📈 Rarity Breakdown",
            value=rarity_text,
            inline=True
        )

        # Era breakdown
        era_text = "\n".join([
            f"{era}: {count}"
            for era, count in era_counts.items()
        ]) or "None"
        embed.add_field(
            name="🎭 Era Breakdown",
            value=era_text,
            inline=True
        )

        await ctx.reply(embed=embed)

    except Exception as e:
        print(f"Error in stats command: {e}")
        await ctx.reply("An error occurred while fetching stats. Please try again.")


@slash_command(name='cooldown', aliases=('cd',))
async def cooldown(ctx):
    """Show the time remaining on your cooldowns."""
    cooldown_labels = {
        'daily': '📅 Daily',
        'weekly': '🗓️ Weekly',
        'drop': '🎴 Drop',
        'spin': '🎰 Spin',
        'train': 'Train',
        'perform': 'Perform',
        'hunt': '🌲 Hunt',
        'claim': '🙋 Claim',
        'trivia': '🧠 Trivia',
    }
    now = time.time()
    today = datetime.date.today().isoformat()

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                '''SELECT cooldown_type, expires_at FROM cooldowns
                   WHERE user_id=? AND expires_at>?''',
                (ctx.author.id, now)
            )
            active_cooldowns = {
                cooldown_type: expires_at
                for cooldown_type, expires_at in c.fetchall()
            }
            c.execute(
                "SELECT spin_date, spins FROM spin_usage WHERE user_id=?",
                (ctx.author.id,),
            )
            spin_usage = c.fetchone()
            spins_used = (
                spin_usage[1]
                if spin_usage and spin_usage[0] == today
                else 0
            )

        embed = discord.Embed(title="Cooldowns", color=0xff6b8b)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        cooldown_types = list(cooldown_labels)
        cooldown_types.extend(sorted(
            set(active_cooldowns) - set(cooldown_labels)
        ))

        for cooldown_type in cooldown_types:
            expires_at = active_cooldowns.get(cooldown_type)
            if cooldown_type == "spin":
                if spins_used >= SPIN_DAILY_LIMIT:
                    reset_at = expires_at or next_local_midnight_timestamp(today)
                    remaining = max(0, int(reset_at - now))
                    days, remainder = divmod(remaining, 86400)
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
                    remaining_text = (
                        f"Limit reached ({spins_used}/{SPIN_DAILY_LIMIT}) "
                        f"• resets in {' '.join(parts)}"
                    )
                else:
                    remaining_text = (
                        f"{spins_used}/{SPIN_DAILY_LIMIT} used • "
                        f"{SPIN_DAILY_LIMIT - spins_used} left today"
                    )
            elif expires_at is None:
                remaining_text = "Ready ✅"
            else:
                remaining = max(0, int(expires_at - now))
                days, remainder = divmod(remaining, 86400)
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
                remaining_text = " ".join(parts)

            label = cooldown_labels.get(cooldown_type)
            if label is None:
                label = f"⏳ {cooldown_type.replace('_', ' ').title()}"
            embed.add_field(
                name=label,
                value=remaining_text,
                inline=False
            )

        await ctx.reply(embed=embed)
    except Exception as e:
        print(f"Error in cooldown command: {e}")
        await ctx.reply("An error occurred while checking your cooldowns.")


@slash_command(
    name='remind',
    aliases=('reminder', 'reminders'),
    descriptions={
        "daily": "DM me when my daily cooldown resets.",
        "weekly": "DM me when my weekly cooldown resets.",
        "drop": "DM me when my drop cooldown resets.",
        "spin": "DM me when my spin cooldown resets.",
        "train": "DM me when my training cooldown resets.",
        "perform": "DM me when my performance cooldown resets.",
        "hunt": "DM me when my hunt cooldown resets.",
        "claim": "DM me when I can claim a card again.",
        "trivia": "DM me when I can play trivia again.",
    },
)
async def cooldown_reminders(
    ctx,
    daily: bool = None,
    weekly: bool = None,
    drop: bool = None,
    spin: bool = None,
    train: bool = None,
    perform: bool = None,
    hunt: bool = None,
    claim: bool = None,
    trivia: bool = None,
):
    """Set any combination of cooldown reminders on or off."""
    now = time.time()
    requested_settings = {
        "daily": daily,
        "weekly": weekly,
        "drop": drop,
        "spin": spin,
        "train": train,
        "perform": perform,
        "hunt": hunt,
        "claim": claim,
        "trivia": trivia,
    }

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                '''INSERT OR IGNORE INTO cooldown_reminders
                   (user_id, cooldown_type, enabled, expires_at)
                   VALUES (?, ?, 0, NULL)''',
                (
                    (ctx.author.id, cooldown_type)
                    for cooldown_type in COOLDOWN_REMINDER_TYPES
                ),
            )

            selected_types = [
                cooldown_type
                for cooldown_type, setting in requested_settings.items()
                if setting is not None
            ]
            for selected_type in selected_types:
                enabled = requested_settings[selected_type]
                expires_at = None
                if enabled:
                    cursor.execute(
                        '''SELECT expires_at FROM cooldowns
                           WHERE user_id=? AND cooldown_type=? AND expires_at>?''',
                        (ctx.author.id, selected_type, now),
                    )
                    active_cooldown = cursor.fetchone()
                    if active_cooldown:
                        expires_at = active_cooldown[0]
                cursor.execute(
                    '''UPDATE cooldown_reminders
                       SET enabled=?, expires_at=?
                       WHERE user_id=? AND cooldown_type=?''',
                    (
                        int(enabled),
                        expires_at,
                        ctx.author.id,
                        selected_type,
                    ),
                )

            cursor.execute(
                '''SELECT cooldown_type, enabled FROM cooldown_reminders
                   WHERE user_id=?''',
                (ctx.author.id,),
            )
            settings = dict(cursor.fetchall())
    except sqlite3.Error as error:
        print(f"Database error while updating cooldown reminders: {error}")
        await ctx.reply("Your reminder settings couldn't be saved due to a database error.")
        return

    settings_text = "\n".join(
        f"**{label}:** {'On' if settings.get(cooldown_type, 0) else 'Off'}"
        for cooldown_type, (label, _) in COOLDOWN_REMINDER_TYPES.items()
    )
    if selected_types:
        changed_labels = ", ".join(
            f"{COOLDOWN_REMINDER_TYPES[cooldown_type][0]} "
            f"{'on' if requested_settings[cooldown_type] else 'off'}"
            for cooldown_type in selected_types
        )
        await ctx.reply(
            f"Updated reminders: {changed_labels}.\n\n{settings_text}"
        )
    else:
        await ctx.reply(
            "Cooldown reminder settings (sent by DM):\n"
            f"{settings_text}\n\n"
            "Set any combination of reminder options to on or off in one command. "
            "Options you leave unset won't change."
        )


@slash_command(name='help')
async def help_command(ctx, *, command_name: str = ""):
    """Show command categories or get usage details for a command."""
    command_name = command_name.strip()
    if command_name:
        command = SLASH_COMMANDS.get(command_name.casefold())
        if command is None:
            await ctx.reply(
                f"I couldn't find `/{command_name}`. Use `/help` "
                "to browse available commands."
            )
            return

        qualified_name = getattr(command, "qualified_name", command.name)
        usage = f"/{qualified_name}"
        for parameter in getattr(command, "parameters", ()):
            marker = "<" if parameter.required else "["
            closing_marker = ">" if parameter.required else "]"
            usage += f" {marker}{parameter.name}{closing_marker}"
        embed = discord.Embed(
            title=f"Help • /{qualified_name}",
            description=command.description or "No description available.",
            color=0xff6b8b,
        )
        embed.add_field(name="Usage", value=f"`{usage}`", inline=False)
        aliases = SLASH_COMMAND_ALIASES.get(command.name, ())
        if aliases:
            embed.add_field(
                name="Aliases",
                value=", ".join(f"`/{alias}`" for alias in aliases),
                inline=False,
            )
        if isinstance(command, app_commands.Group) and command.commands:
            subcommands = " • ".join(
                f"`/{command.name} {subcommand.name}`"
                for subcommand in command.commands
            )
            embed.add_field(name="Subcommands", value=subcommands, inline=False)
        await ctx.reply(embed=embed)
        return

    view = HelpView(ctx)
    await ctx.reply(embed=view.get_embed(), view=view)


@slash_command(name='afk')
async def afk(ctx, *, reason: str = "AFK"):
    """Set an AFK status that clears when you send another message."""
    if ctx.guild is None:
        await ctx.reply("AFK status can only be set in a server.")
        return

    reason = reason.strip() or "AFK"
    if len(reason) > 500:
        await ctx.reply("Your AFK reason must be 500 characters or fewer.")
        return

    try:
        set_guild_afk(ctx.guild.id, ctx.author.id, reason, time.time())
    except sqlite3.Error as error:
        print(f"Database error while setting AFK status: {error}")
        await ctx.reply("Your AFK status couldn't be saved due to a database error.")
        return

    await ctx.reply(
        f"{ctx.author.display_name} is now AFK: {reason}",
        allowed_mentions=discord.AllowedMentions.none(),
    )
