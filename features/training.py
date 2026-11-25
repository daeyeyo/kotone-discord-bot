import random
import sqlite3
import discord
from kotone.client import (
    slash_command,
)
from kotone.game import (
    get_preferred_card,
    perform_card,
    save_preferred_card,
    train_card,
)
from kotone.images import (
    get_card_image,
)


SONGS = (
    "Access",
    "Generation",
    "Rolex",
    "Charla",
    "Dimension",
    "+(82)",
    "Beam",
    "Before the Rise",
    "Rising",
    "Colorful",
    "The Baddest",
    "New Look",
    "Chowall",
    "Cherry 100%",
    "Cherry Talk",
    "Touch",
    "Hide & Seek",
    "Deja-Vu",
    "Touch+",
    "Cherry Gene",
    "Girls’ Capitalism",
    "Complexity",
    "Black Soul Dress",
    "Seoul Sonyo Sound",
    "Cry Baby",
    "Speed Love",
    "Mujuk",
    "Invincible",
    "Rhodanthe",
    "Heavy Metal Wings",
    "37.5 Celsius",
    "Moto Princess",
    "Oui",
    "Enhanced Flower",
    "Just Do It",
    "Door",
    "Farewell My First",
    "S",
    "Girls Never Die",
    "Heart Raider",
    "Midnight Flower",
    "White Soul Sneakers",
    "Chiyu",
    "24",
    "Beyond the Beyond",
    "Non Scale",
    "Inner Dance",
    "Visual Virtue",
    "Hit the Floor",
    "Choom",
    "Éclair",
    "Love Soseol",
    "Atmosphere",
    "12 Rings",
    "Vision",
    "Bionic Power",
    "Visionary Vision",
    "Polaroid",
    "Dreaming",
    "Untitled (アンタイトル)",
    "(Hash)",
    "@% (Alpha Percent)",
    "Are You Alive",
    "Detective Soseol",
    "Firework Diary",
    "Love Child",
    "Persona",
    "Too Hot",
    "Diablo",
    "Friend Zone",
    "Love2Love",
    "PinkPower",
    "Paindrop",
    "Password",
    "Headphones",
    "Tokimetique",
    "TOKYO",
    "Oshare",
    "Magic Shine New Zone",
    "Fly Up",
    "Cameo Love",
    "Bubble Gum Girl",
    "Q&A",
    "Christmas Alone",
    "Sad Girls Schemin’",
    "Peer",
    "Baby Flower",
    "Type of Girl",
    "Sleek",
    "I Like That",
    "Me Myself Mode",
    "World Wild Women",
    "Dream Dress",
    "DNA",
    "Welcome to Heaven",
    "Andless",
)
PRACTICE_ACTIONS = {
    "Vocals": (
        "ran vocal drills for",
        "practiced the high notes of",
        "worked on the ad-libs for",
        "did a full vocal run of",
    ),
    "Dance": (
        "practiced the choreography for",
        "drilled the dance break of",
        "worked on the formations for",
        "rehearsed the stage for",
    ),
    "Rap": (
        "worked on the rap verse for",
        "practiced the flow for",
        "ran through the rap line of",
        "tightened up the delivery for",
    ),
}
PRACTICE_SPOTS = (
    "the practice room",
    "the dance studio",
    "the vocal booth",
    "the company rooftop",
    "the late-night rehearsal room",
    "the mirrored practice hall",
)
PERFORM_VENUES = (
    "Yonsei University Festival",
    "Korea University Festival",
    "Hongdae Street Stage",
    "Music Bank pre-recording",
    "Inkigayo stage",
    "a sold-out fan meeting in Seoul",
    "the Tokyo showcase",
    "the Seoul Olympic Hall",
    "a campus festival in Busan",
)
GRADE_REACTIONS = {
    "S": "The crowd went wild — they had to do an encore!",
    "A": "The crowd loved every second of it!",
    "B": "A solid stage with plenty of cheers.",
    "C": "The fans still cheered them on.",
}


@slash_command(
    name="train",
    descriptions={
        "serial": "Train this card instead of your saved default.",
        "set": "Save this card as your default training card.",
    },
)
async def train(ctx, serial: str = None, set: str = None):
    """Train a card's specialty skill (4h cooldown)."""
    if serial is not None and set is not None:
        await ctx.reply("Use either `serial` or `set`, not both.")
        return
    if set is not None:
        try:
            selected_serial = save_preferred_card(ctx.author.id, "train", set)
        except ValueError as error:
            await ctx.reply(str(error))
            return
        except sqlite3.Error as error:
            print(f"Error saving default training card: {error}")
            await ctx.reply("The default training card couldn't be saved.")
            return
        await ctx.reply(
            f"Your default training card is now `{selected_serial}`. "
            "Use `/train` to train it, or provide `serial` to train another."
        )
        return

    try:
        if serial is not None:
            selected_serial = serial.strip()
            if not selected_serial:
                raise ValueError("Enter a valid card serial.")
        else:
            selected_serial = get_preferred_card(ctx.author.id, "train")
        result = train_card(ctx.author.id, selected_serial)
    except ValueError as error:
        await ctx.reply(str(error))
        return
    except Exception as error:
        print(f"Error in train command: {error}")
        await ctx.reply("An error occurred while training that card.")
        return

    actions = PRACTICE_ACTIONS.get(
        result["skill"],
        PRACTICE_ACTIONS["Vocals"],
    )
    action = random.choice(actions)
    spot = random.choice(PRACTICE_SPOTS)
    song = random.choice(SONGS)
    perfect = " **Perfect practice!**" if result["perfect"] else ""
    message = (
        f"🎤 **{result['name']}** {action} **{song}** "
        f"at {spot}.\n"
        f"✨ **{result['skill']} +{result['gain']}** "
        f"({result['old_points']} → {result['new_points']}).{perfect}\n"
        f"⚡ Skill points: **{result['points']}** • "
        f"📈 Training sessions: **{result['training_sessions']}**"
    )
    if result["cap_reached"]:
        message += (
            f"\n🏆 {result['skill']} is now at the **{result['rarity']}** "
            f"cap of **{result['cap']}**!"
        )
    message += "\n⏳ Next training available in **4 hours**."
    await ctx.reply(message)


@slash_command(
    name="perform",
    descriptions={
        "serial": "Perform with this card instead of your saved default.",
        "set": "Save this card as your default performance card.",
    },
)
async def perform(ctx, serial: str = None, set: str = None):
    """Perform with a card to earn COMO (4h cooldown)."""
    if serial is not None and set is not None:
        await ctx.reply("Use either `serial` or `set`, not both.")
        return
    if set is not None:
        try:
            selected_serial = save_preferred_card(ctx.author.id, "perform", set)
        except ValueError as error:
            await ctx.reply(str(error))
            return
        except sqlite3.Error as error:
            print(f"Error saving default performance card: {error}")
            await ctx.reply("The default performance card couldn't be saved.")
            return
        await ctx.reply(
            f"Your default performance card is now `{selected_serial}`. "
            "Use `/perform` to perform with it, or provide `serial` to use another."
        )
        return

    try:
        if serial is not None:
            selected_serial = serial.strip()
            if not selected_serial:
                raise ValueError("Enter a valid card serial.")
        else:
            selected_serial = get_preferred_card(ctx.author.id, "perform")
        result = perform_card(
            ctx.author.id,
            str(ctx.author),
            selected_serial,
        )
    except ValueError as error:
        await ctx.reply(str(error))
        return
    except Exception as error:
        print(f"Error in perform command: {error}")
        await ctx.reply("An error occurred while performing with that card.")
        return

    venue = random.choice(PERFORM_VENUES)
    song = random.choice(SONGS)
    embed = discord.Embed(
        title=f"🎤 {result['name']} — {song}",
        description=(
            f"🎶 **{result['name']}** performed **{song}** at "
            f"**{venue}**!\n🎉 {GRADE_REACTIONS[result['grade']]}"
        ),
        color=0xff6b8b,
    )
    embed.set_thumbnail(
        url=get_card_image(
            result["era"],
            result["member_code"],
            result["rarity"],
            animated=True,
        )
    )
    embed.add_field(
        name="🏅 Grade",
        value=f"**{result['grade']}**",
        inline=True,
    )
    embed.add_field(
        name="✨ Skill",
        value=(
            f"{result['skill']} **{result['points']}** / "
            f"{result['cap']}"
        ),
        inline=True,
    )
    embed.add_field(
        name="💰 COMO earned",
        value=f"+**{result['payout']:,}**",
        inline=True,
    )
    embed.add_field(
        name="🪙 New balance",
        value=f"**{result['new_balance']:,} COMO**",
        inline=True,
    )
    embed.add_field(
        name="🎤 Performances",
        value=f"**{result['performances']}**",
        inline=True,
    )
    embed.set_footer(
        text=f"{result['serial']} • ⏳ Next performance in 4 hours"
    )
    await ctx.reply(embed=embed)
