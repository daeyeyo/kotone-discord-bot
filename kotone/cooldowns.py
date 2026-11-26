import asyncio
import datetime
import sqlite3
import time
import discord
from discord.ext import tasks
from kotone.client import (
    bot,
)
from kotone.db import (
    get_db,
)


# Cooldown management functions
COOLDOWN_REMINDER_TYPES = {
    "daily": ("Daily", "/daily"),
    "weekly": ("Weekly", "/weekly"),
    "drop": ("Drop", "/drop"),
    "spin": ("Spin", "/spin serial"),
    "train": ("Training", "/train"),
    "perform": ("Perform", "/perform"),
    "hunt": ("Hunt", "/hunt"),
    "claim": ("Claim", None),
    "trivia": ("Trivia", "/trivia"),
}

def schedule_cooldown_reminder(cursor, user_id, cooldown_type, expires_at):
    cursor.execute(
        '''UPDATE cooldown_reminders SET expires_at=?
           WHERE user_id=? AND cooldown_type=? AND enabled=1''',
        (expires_at, user_id, cooldown_type),
    )


def next_local_midnight_timestamp(day=None):
    current_day = (
        datetime.date.fromisoformat(day)
        if day is not None
        else datetime.date.today()
    )
    tomorrow = current_day + datetime.timedelta(days=1)
    return datetime.datetime.combine(tomorrow, datetime.time.min).timestamp()


@tasks.loop(seconds=30)
async def cooldown_reminder_loop():
    now = time.time()
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cooldowns WHERE expires_at <= ?", (now,))
            cursor.execute(
                '''SELECT user_id, cooldown_type, expires_at
                   FROM cooldown_reminders
                   WHERE enabled=1 AND expires_at IS NOT NULL AND expires_at<=?''',
                (now,),
            )
            due_reminders = cursor.fetchall()
    except sqlite3.Error as error:
        print(f"Database error while checking cooldown reminders: {error}")
        return

    for index, (user_id, cooldown_type, expires_at) in enumerate(due_reminders):
        if index:
            await asyncio.sleep(1)

        cooldown_label, command_hint = COOLDOWN_REMINDER_TYPES.get(
            cooldown_type,
            (cooldown_type.replace("_", " ").title(), cooldown_type),
        )
        try:
            user = bot.get_user(user_id) or await bot.fetch_user(user_id)
            reminder_message = f"Your **{cooldown_label}** cooldown has reset."
            if command_hint:
                reminder_message += f" You can use `{command_hint}` again."
            else:
                reminder_message += " You can claim a card again."
            await user.send(
                reminder_message
            )
        except discord.HTTPException as error:
            print(
                f"Could not send {cooldown_type} cooldown reminder "
                f"to user {user_id}: {error}"
            )
            if error.status == 429:
                try:
                    with get_db() as conn:
                        conn.execute(
                            '''UPDATE cooldown_reminders SET expires_at=?
                               WHERE user_id=? AND cooldown_type=? AND expires_at=?''',
                            (time.time() + 60, user_id, cooldown_type, expires_at),
                        )
                except sqlite3.Error as database_error:
                    print(
                        f"Database error while deferring rate-limited "
                        f"{cooldown_type} reminder for user {user_id}: "
                        f"{database_error}"
                    )
                return

        try:
            with get_db() as conn:
                conn.execute(
                    '''UPDATE cooldown_reminders SET expires_at=NULL
                       WHERE user_id=? AND cooldown_type=? AND expires_at=?''',
                    (user_id, cooldown_type, expires_at),
                )
        except sqlite3.Error as error:
            print(
                f"Database error while clearing {cooldown_type} cooldown "
                f"reminder for user {user_id}: {error}"
            )

def check_cooldown(user_id: int, cooldown_type: str, duration: int) -> tuple[bool, int]:
    """
    Check if user is on cooldown.
    Returns (is_on_cooldown, remaining_seconds)
    """
    current_time = time.time()

    with get_db() as conn:
        c = conn.cursor()
        c.execute('''SELECT expires_at FROM cooldowns 
                     WHERE user_id=? AND cooldown_type=?''', 
                  (user_id, cooldown_type))
        result = c.fetchone()

    if result:
        remaining = int(result[0] - current_time)
        if remaining > 0:
            return True, remaining

    return False, 0

def set_cooldown(user_id: int, cooldown_type: str, duration: int):
    """Set a cooldown for a user."""
    expires_at = time.time() + duration
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO cooldowns 
                     (user_id, cooldown_type, expires_at) 
                     VALUES (?, ?, ?)''',
                  (user_id, cooldown_type, expires_at))
        schedule_cooldown_reminder(
            c,
            user_id,
            cooldown_type,
            expires_at,
        )
