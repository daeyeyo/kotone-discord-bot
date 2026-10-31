import asyncio
import inspect
import math
import os
import signal
import time
from types import SimpleNamespace
import discord
from discord import app_commands


# Bot setup
intents = discord.Intents.default()
intents.message_content = True


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
