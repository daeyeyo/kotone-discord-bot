import asyncio
import inspect
import math
import os
import re
import signal
import time
from types import SimpleNamespace
import discord
from discord import app_commands


# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


USER_NAME_CACHE_TTL = 3600
USER_NAME_NOT_FOUND_TTL = 300
USER_NAME_ERROR_TTL = 60

_USER_NAME_CACHE = {}
_PLACEHOLDER_USERNAME_RE = re.compile(r"^user_\d+$", re.IGNORECASE)
_SYNTHETIC_COLLECTOR_RE = re.compile(r"^900000000000000(\d{3,})$")


def is_placeholder_username(username):
    """Return True if a stored username is missing or a synthetic placeholder."""
    if username is None:
        return True
    cleaned = str(username).strip()
    if not cleaned:
        return True
    if _PLACEHOLDER_USERNAME_RE.fullmatch(cleaned):
        return True
    return cleaned.casefold() in ("unknown", "unknown user")


def is_synthetic_user_id(user_id):
    """Return True if user_id matches the synthetic collector ID range."""
    if user_id is None:
        return False
    return bool(_SYNTHETIC_COLLECTOR_RE.fullmatch(str(user_id).strip()))


def format_fallback_display_name(user_id):
    """Return a clean fallback label for IDs without a stored or Discord name."""
    raw = str(user_id).strip()
    match = _SYNTHETIC_COLLECTOR_RE.fullmatch(raw)
    if match:
        return f"Collector #{match.group(1)}"
    return f"user_{raw[-4:]}"


def invalidate_user_name_cache(user_id):
    """Evict a user from the in-memory Discord name cache."""
    _USER_NAME_CACHE.pop(user_id, None)


def preferred_discord_display_name(user):
    """Return the user's preferred Discord display name."""
    return (
        getattr(user, "display_name", None)
        or getattr(user, "global_name", None)
        or getattr(user, "name", None)
        or str(user)
    ).strip()


def get_cached_discord_user(client, user_id, guild=None):
    """Look up a Discord Member/User from in-memory gateway caches only."""
    if guild is not None:
        member = guild.get_member(user_id)
        if member is not None:
            return member
    user = client.get_user(user_id)
    if user is not None:
        return user
    for cached_guild in getattr(client, "guilds", ()):
        member = cached_guild.get_member(user_id)
        if member is not None:
            return member
    return None


async def resolve_discord_user_info(
    client,
    user_id,
    *,
    guild=None,
    stored_display_name=None,
    stored_username=None,
    fetch_budget=None,
):
    """Resolve (display_name, fetched_names, discord_user) with DB-first priority.

    Priority order:
    1. Stored `display_name` or `username` in `kpop_cards.db`.
    2. Live Discord cache / `await client.fetch_user(user_id)` (returns
       `fetched_names = (display_name, username)` so callers can persist it).
    3. Clean fallback (`Collector #008` for synthetic IDs, else `user_<last4>`).
    """
    cached_user = get_cached_discord_user(client, user_id, guild=guild)
    for candidate in (stored_display_name, stored_username):
        if candidate and not is_placeholder_username(candidate):
            return str(candidate).strip(), None, cached_user

    if is_synthetic_user_id(user_id):
        return format_fallback_display_name(user_id), None, None

    if cached_user is not None:
        display_name = preferred_discord_display_name(cached_user)
        username = (getattr(cached_user, "name", None) or str(cached_user)).strip()
        _USER_NAME_CACHE[user_id] = (
            display_name,
            username,
            time.monotonic() + USER_NAME_CACHE_TTL,
        )
        return display_name, (display_name, username), cached_user

    now = time.monotonic()
    cached_entry = _USER_NAME_CACHE.get(user_id)
    skip_fetch = False
    if cached_entry is not None:
        cached_display, cached_username, expires_at = cached_entry
        if expires_at > now:
            if cached_display is not None:
                return cached_display, (cached_display, cached_username), None
            skip_fetch = True

    if not skip_fetch and fetch_budget is not None:
        if fetch_budget[0] <= 0:
            skip_fetch = True
        else:
            fetch_budget[0] -= 1

    if not skip_fetch:
        try:
            fetched = await client.fetch_user(user_id)
        except discord.NotFound:
            _USER_NAME_CACHE[user_id] = (
                None,
                None,
                time.monotonic() + USER_NAME_NOT_FOUND_TTL,
            )
        except (discord.HTTPException, asyncio.TimeoutError) as error:
            print(f"Could not fetch Discord user {user_id}: {error}")
            _USER_NAME_CACHE[user_id] = (
                None,
                None,
                time.monotonic() + USER_NAME_ERROR_TTL,
            )
        else:
            display_name = preferred_discord_display_name(fetched)
            username = (getattr(fetched, "name", None) or str(fetched)).strip()
            _USER_NAME_CACHE[user_id] = (
                display_name,
                username,
                time.monotonic() + USER_NAME_CACHE_TTL,
            )
            return display_name, (display_name, username), fetched

    return format_fallback_display_name(user_id), None, None


def format_uptime(seconds):
    seconds = max(0, int(seconds))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


class KotoneBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.status_channel_id = None
        self.status_channel_checked = False
        self.offline_status_sent = False
        self.status_start_time = None
        self.sigterm_task = None
        self._post_command_hooks = []
        self._cached_app_info = None

    async def is_bot_owner(self, user_id):
        """Return True if user_id is the configured bot owner or team member."""
        env_owner = os.getenv("BOT_OWNER_ID", "").strip()
        if env_owner:
            owner_ids = {
                int(part)
                for part in env_owner.split(",")
                if part.strip().isdigit()
            }
            if user_id in owner_ids:
                return True

        if self._cached_app_info is None:
            try:
                self._cached_app_info = await self.application_info()
            except Exception:
                return False

        app_info = self._cached_app_info
        if app_info is None:
            return False
        team = getattr(app_info, "team", None)
        if team is not None:
            return any(member.id == user_id for member in team.members)
        owner = getattr(app_info, "owner", None)
        return owner is not None and owner.id == user_id

    async def setup_hook(self):
        # Docker stops the bot with SIGTERM. Close cleanly so "Offline" is posted.
        # Windows event loops do not support signal handlers.
        try:
            asyncio.get_running_loop().add_signal_handler(
                signal.SIGTERM,
                self.handle_sigterm,
            )
        except (NotImplementedError, RuntimeError):
            pass
        await self.tree.sync()
        print(f"Synced {len(self.tree.get_commands())} slash commands")

    def handle_sigterm(self):
        if self.sigterm_task is None:
            self.sigterm_task = asyncio.create_task(self.close())

    def get_status_channel_id(self):
        if not self.status_channel_checked:
            self.status_channel_checked = True
            value = os.getenv("STATUS_CHANNEL_ID", "").strip()
            if value.isascii() and value.isdigit() and int(value) > 0:
                self.status_channel_id = int(value)
            elif value:
                print("STATUS_CHANNEL_ID is not a valid channel ID. Status messages are off.")
            else:
                print("STATUS_CHANNEL_ID is not set. Status messages are off.")
        return self.status_channel_id

    STATUS_GIF_URL = "https://pub-6b36c51f5c9a4d9c884ee896543879d9.r2.dev/tripleS-kotone-punch.gif"

    def build_status_embed(self, status):
        if status == "Online":
            embed = discord.Embed(
                title="Online",
                color=0x2ECC71,
                timestamp=discord.utils.utcnow(),
            )
            latency = self.latency * 1000
            embed.add_field(name="Servers", value=str(len(self.guilds)))
            embed.add_field(
                name="Commands",
                value=str(len(self.tree.get_commands())),
            )
            embed.add_field(
                name="Latency",
                value=f"{round(latency)} ms" if math.isfinite(latency) else "n/a",
            )
            embed.set_thumbnail(url=self.STATUS_GIF_URL)
        else:
            embed = discord.Embed(
                title="Offline",
                color=0xE74C3C,
                timestamp=discord.utils.utcnow(),
            )
            if self.status_start_time is not None:
                embed.add_field(
                    name="Uptime",
                    value=format_uptime(time.monotonic() - self.status_start_time),
                )
        return embed

    async def send_status(self, status):
        channel_id = self.get_status_channel_id()
        if channel_id is None:
            return
        try:
            embed = self.build_status_embed(status)
            channel = self.get_partial_messageable(channel_id)
            await asyncio.wait_for(channel.send(embed=embed), timeout=5)
        except Exception as error:
            print(f"Could not post status message: {error!r}")

    async def close(self):
        try:
            if (
                not self.offline_status_sent
                and self.is_ready()
                and not self.is_closed()
            ):
                self.offline_status_sent = True
                await self.send_status("Offline")
        finally:
            await super().close()

bot = KotoneBot()
SLASH_COMMANDS = {}
SLASH_COMMAND_ALIASES = {}


class SlashContext:
    def __init__(self, interaction, invoked_with, members):
        self.interaction = interaction
        self.author = interaction.user
        self.guild = interaction.guild
        self.channel = interaction.channel
        self.bot = interaction.client
        self.invoked_with = invoked_with
        self.message = SimpleNamespace(mentions=members)

    async def reply(self, content=None, **kwargs):
        kwargs.pop("mention_author", None)
        return await self.interaction.followup.send(
            content=content,
            wait=True,
            **kwargs,
        )

    async def send(self, content=None, **kwargs):
        return await self.reply(content, **kwargs)


def slash_command(
    name=None,
    *,
    aliases=(),
    group=None,
    autocomplete=None,
    descriptions=None,
):
    def decorator(callback):
        callback_signature = inspect.signature(callback)
        option_parameters = []
        for parameter in list(callback_signature.parameters.values())[1:]:
            annotation = parameter.annotation
            if annotation is inspect.Parameter.empty:
                annotation = str
            option_parameters.append(
                parameter.replace(
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=annotation,
                )
            )

        async def invoke(interaction, **options):
            await interaction.response.defer(thinking=True)
            members = [
                value
                for value in options.values()
                if isinstance(value, discord.Member)
            ]
            context = SlashContext(
                interaction,
                interaction.data.get("name", command_name),
                members,
            )
            await callback(context, **options)
            for hook in getattr(bot, "_post_command_hooks", ()):
                try:
                    result = hook(interaction)
                    if inspect.isawaitable(result):
                        await result
                except Exception as hook_error:
                    print(f"Post-command hook failed: {hook_error}")

        command_name = name or callback.__name__
        command_description = (callback.__doc__ or "Run this command.").strip()
        command_description = command_description.splitlines()[0][:100]
        parameters = [
            inspect.Parameter(
                "interaction",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=discord.Interaction,
            ),
            *option_parameters,
        ]
        invoke.__signature__ = inspect.Signature(parameters)
        invoke.__annotations__ = {
            parameter.name: parameter.annotation for parameter in parameters
        }
        if descriptions:
            invoke.__discord_app_commands_param_description__ = descriptions
        if autocomplete:
            app_commands.autocomplete(**autocomplete)(invoke)

        for registered_name in (command_name, *aliases):
            SLASH_COMMAND_ALIASES[registered_name] = tuple(
                alias
                for alias in (command_name, *aliases)
                if alias != registered_name
            )
            command = app_commands.Command(
                name=registered_name,
                description=command_description,
                callback=invoke,
            )
            if group is None:
                bot.tree.add_command(command)
            else:
                group.add_command(command)
            command_key = (
                f"{group.name} {registered_name}"
                if group is not None
                else registered_name
            )
            SLASH_COMMANDS[command_key] = command
        return callback

    return decorator
