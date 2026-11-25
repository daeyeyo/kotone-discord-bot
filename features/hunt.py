import sqlite3

import discord

from kotone.client import slash_command
from kotone.game import (
    get_preferred_card,
    hunt_card,
    save_preferred_card,
)
from kotone.images import get_card_image


@slash_command(
    name="hunt",
    descriptions={
        "serial": "Hunt with this card instead of your saved default.",
        "set": "Save this card as your default hunting card.",
    },
)
async def hunt(ctx, serial: str = None, set: str = None):
    """Send a card hunting for COMO and another card (4h cooldown)."""
    if serial is not None and set is not None:
        await ctx.reply("Use either `serial` or `set`, not both.")
        return
    if set is not None:
        try:
            selected_serial = save_preferred_card(ctx.author.id, "hunt", set)
        except ValueError as error:
            await ctx.reply(str(error))
            return
        except sqlite3.Error as error:
            print(f"Error saving default hunting card: {error}")
            await ctx.reply("The default hunting card couldn't be saved.")
            return
        await ctx.reply(
            f"Your default hunting card is now `{selected_serial}`. "
            "Use `/hunt` to send it hunting, or provide `serial` to use another."
        )
        return

    try:
        if serial is not None:
            selected_serial = serial.strip()
            if not selected_serial:
                raise ValueError("Enter a valid card serial.")
        else:
            selected_serial = get_preferred_card(ctx.author.id, "hunt")
        result = hunt_card(ctx.author.id, str(ctx.author), selected_serial)
    except ValueError as error:
        await ctx.reply(str(error))
        return
    except (sqlite3.Error, RuntimeError) as error:
        print(f"Error in hunt command: {error}")
        await ctx.reply("An error occurred while your card was hunting.")
        return

    reward_card = result["reward_card"]
    embed = discord.Embed(
        title="🌲 Hunt Successful!",
        description=(
            f"**{result['hunting_card_name']}** returned from the forest "
            f"with **{reward_card['rarity']} "
            f"{reward_card['name']}** (`{reward_card['serial']}`) "
            f"and **{result['payout']:,} COMO**!"
        ),
        color=0x5ca878,
    )
    embed.set_thumbnail(
        url=get_card_image(
            reward_card["era"],
            reward_card["member_code"],
            reward_card["rarity"],
            animated=True,
        )
    )
    embed.add_field(
        name="Hunting card",
        value=(
            f"{result['hunting_rarity']} • {result['skill']} "
            f"**{result['points']}/{result['cap']}**"
        ),
        inline=True,
    )
    if result["training_sessions"]:
        embed.add_field(
            name="Training bonus",
            value=f"{result['training_bonus']:.0%}",
            inline=True,
        )
    embed.add_field(
        name="New balance",
        value=f"**{result['new_balance']:,} COMO**",
        inline=True,
    )
    embed.set_footer(text="The forest will be ready for another hunt in 4 hours.")
    await ctx.reply(embed=embed)
