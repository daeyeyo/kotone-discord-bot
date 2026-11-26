import re
import sqlite3
import time
import discord
from discord import app_commands
from kotone.client import (
    bot,
    preferred_discord_display_name,
)
from kotone.cooldowns import (
    cooldown_reminder_loop,
)
from kotone.db import (
    clear_guild_afk,
    get_guild_afk_statuses,
    load_afk_cache,
    sync_user_username,
)

# on_ready runs again after every reconnect, so "Online" is posted only once.
online_status_sent = False


@bot.event
async def on_ready():
    global online_status_sent
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guilds')
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(
            name="Andless",
            type=discord.ActivityType.listening,
            details="YouTube",
            details_url="https://www.youtube.com/watch?v=uqJ6GDJSyfY",
            state="Spotify",
            state_url="https://open.spotify.com/track/54E6zLaoW4ofXKaXhLVu3G",
        ),
    )
    if not cooldown_reminder_loop.is_running():
        cooldown_reminder_loop.start()
    try:
        load_afk_cache()
    except sqlite3.Error as error:
        print(f"Database error while loading AFK cache: {error}")
    if not online_status_sent:
        online_status_sent = True
        await bot.send_status("Online")
        # Uptime in the "Offline" message counts from here.
        bot.status_start_time = time.monotonic()


def format_afk_duration(elapsed_seconds):
    units = (
        (365 * 86400, "year"),
        (30 * 86400, "month"),
        (7 * 86400, "week"),
        (86400, "day"),
        (3600, "hour"),
        (60, "minute"),
        (1, "second"),
    )
    elapsed_seconds = max(1, int(elapsed_seconds))
    for unit_seconds, unit_name in units:
        if elapsed_seconds >= unit_seconds:
            count = elapsed_seconds // unit_seconds
            plural = "" if count == 1 else "s"
            return f"{count} {unit_name}{plural}"
    return "1 second"


# -------------------- NEW COMMANDS --------------------



# -------------------------------------------------------

@bot.event
async def on_message(message):
    # Don't respond to ourselves
    if message.author == bot.user:
        return

    afk_responses = []
    if message.guild is not None:
        guild_id = message.guild.id
        mentioned_users = {
            user.id: user
            for user in message.mentions
            if user.id != message.author.id and not user.bot
        }
        try:
            if clear_guild_afk(guild_id, message.author.id):
                afk_responses.append(
                    f"Welcome back, **{message.author.display_name}**! "
                    "Your AFK status has been removed."
                )

            if mentioned_users:
                now = time.time()
                for user_id, reason, since in get_guild_afk_statuses(
                    guild_id,
                    mentioned_users,
                ):
                    mentioned_user = mentioned_users[user_id]
                    duration = format_afk_duration(now - since)
                    visible_reason = reason
                    if len(visible_reason) > 300:
                        visible_reason = visible_reason[:297] + "..."
                    afk_responses.append(
                        f"**{mentioned_user.display_name}** is AFK: "
                        f"{visible_reason} — {duration} ago."
                    )
        except sqlite3.Error as error:
            print(f"Database error while checking AFK statuses: {error}")
            afk_responses.append(
                "AFK statuses couldn't be checked due to a database error."
            )

    if afk_responses:
        response = []
        response_length = 0
        for afk_response in afk_responses:
            if response_length + len(afk_response) + 1 > 1900:
                response.append("More AFK statuses were omitted.")
                break
            response.append(afk_response)
            response_length += len(afk_response) + 1
        await message.reply(
            "\n".join(response),
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    
    # Only respond to direct greeting messages, not commands or quoted examples.
    greeting = message.content.strip()
    kotone_greeting = re.fullmatch(
        r"(?:hi|hello|hey)\s+(?:kotone|tone)[.!?]*",
        greeting,
        re.IGNORECASE,
    )
    kotone_goodnight = re.fullmatch(
        r"(?:good\s*night|night)\s+(?:kotone|tone)[.!?]*",
        greeting,
        re.IGNORECASE,
    )
    jiwoo_greeting = re.fullmatch(
        r"(?:hi|hello|hey)\s+jiwoo[.!?]*",
        greeting,
        re.IGNORECASE,
    )

    if kotone_goodnight:
        await message.reply("Good night! 💤")
        await message.channel.send(
            "https://cdn.discordapp.com/attachments/"
            "1335162578246041680/1559482247713923092/"
            "SaveClip.App_723406788_18056502230752032_4643667593876559471_n.jpg"
        )

    elif kotone_greeting:
        await message.reply("Hi!")
        await message.channel.send("https://tenor.com/view/triples-kotone-kpop-s11-kamimoto-kotone-gif-1824783912790233912")

    if jiwoo_greeting:
        await message.reply("Hi!")
        # TODO: replace with a Jiwoo GIF link
        await message.channel.send("https://klipy.com/gifs/lee-jiwoo-jiwoo-triples")


@bot.tree.error
async def on_app_command_error(interaction, error):
    if isinstance(error, app_commands.CommandOnCooldown):
        message = (
            f"This command is on cooldown. Try again in "
            f"{error.retry_after:.1f} seconds."
        )
    else:
        print(f"Error in slash command: {error}")
        message = "An unexpected error occurred. Please try again later."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


def _sync_discord_user_names(user):
    if user is None or getattr(user, "bot", False):
        return
    username = (getattr(user, "name", None) or str(user)).strip()
    display_name = preferred_discord_display_name(user)
    sync_user_username(user.id, username=username, display_name=display_name)


bot._post_command_hooks.append(
    lambda interaction: _sync_discord_user_names(interaction.user)
)
