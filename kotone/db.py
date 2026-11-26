import re
import sqlite3
import time
from contextlib import contextmanager


_SYNCED_USERNAMES = {}
_SYNCED_USERNAME_TTL = 600
_PLACEHOLDER_USERNAME_RE = re.compile(r"^user_\d+$", re.IGNORECASE)
_AFK_CACHE = {}
_AFK_CACHE_LOADED = False


def _clean_non_placeholder_name(value):
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned or _PLACEHOLDER_USERNAME_RE.fullmatch(cleaned):
        return None
    if cleaned.casefold() in ("unknown", "unknown user"):
        return None
    return cleaned


def sync_user_username(
    user_id,
    username=None,
    *,
    display_name=None,
    create_if_missing=False,
):
    """Update a player's stored username and display_name in `users`."""
    if not user_id:
        return
    cleaned_username = _clean_non_placeholder_name(username)
    cleaned_display_name = _clean_non_placeholder_name(display_name)
    if cleaned_username is None and cleaned_display_name is None:
        return

    now = time.monotonic()
    cached = _SYNCED_USERNAMES.get(user_id)
    if (
        cached is not None
        and cached[2] > now
        and not create_if_missing
        and (cleaned_username is None or cached[0] == cleaned_username)
        and (cleaned_display_name is None or cached[1] == cleaned_display_name)
    ):
        return

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            if create_if_missing:
                cursor.execute(
                    '''INSERT INTO users (user_id, username, display_name)
                       VALUES (?, ?, ?)
                       ON CONFLICT(user_id) DO UPDATE SET
                           username = COALESCE(excluded.username, users.username),
                           display_name = CASE
                               WHEN COALESCE(users.custom_display_name, 0) = 0
                               THEN COALESCE(excluded.display_name, users.display_name)
                               ELSE users.display_name
                           END
                       WHERE (excluded.username IS NOT NULL AND (users.username IS NULL OR users.username != excluded.username))
                          OR (COALESCE(users.custom_display_name, 0) = 0
                              AND excluded.display_name IS NOT NULL
                              AND (users.display_name IS NULL OR users.display_name != excluded.display_name))''',
                    (user_id, cleaned_username, cleaned_display_name),
                )
            else:
                cursor.execute(
                    '''UPDATE users
                       SET username = COALESCE(?, username),
                           display_name = CASE
                               WHEN COALESCE(custom_display_name, 0) = 0
                               THEN COALESCE(?, display_name)
                               ELSE display_name
                           END
                       WHERE user_id = ?
                         AND ((? IS NOT NULL AND (username IS NULL OR username != ?))
                              OR (COALESCE(custom_display_name, 0) = 0
                                  AND ? IS NOT NULL
                                  AND (display_name IS NULL OR display_name != ?)))''',
                    (
                        cleaned_username,
                        cleaned_display_name,
                        user_id,
                        cleaned_username,
                        cleaned_username,
                        cleaned_display_name,
                        cleaned_display_name,
                    ),
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        "SELECT 1 FROM users WHERE user_id = ?",
                        (user_id,),
                    )
                    if cursor.fetchone() is None:
                        cursor.execute(
                            "SELECT 1 FROM cards WHERE owner_id = ? LIMIT 1",
                            (user_id,),
                        )
                        if cursor.fetchone() is not None:
                            cursor.execute(
                                "INSERT OR IGNORE INTO users (user_id, username, display_name) VALUES (?, ?, ?)",
                                (user_id, cleaned_username, cleaned_display_name),
                            )
    except sqlite3.Error as error:
        print(f"Could not sync username for {user_id}: {error}")
        return

    next_username = (
        cleaned_username
        if cleaned_username is not None
        else (cached[0] if cached is not None else None)
    )
    next_display_name = (
        cleaned_display_name
        if cleaned_display_name is not None
        else (cached[1] if cached is not None else None)
    )
    _SYNCED_USERNAMES[user_id] = (
        next_username,
        next_display_name,
        time.monotonic() + _SYNCED_USERNAME_TTL,
    )


def set_user_display_name(user_id, display_name):
    """Explicitly set a player's custom display_name in `users`."""
    cleaned = str(display_name).strip() if display_name is not None else ""
    if not cleaned:
        raise ValueError("Display name cannot be empty.")
    if len(cleaned) > 64:
        raise ValueError("Display name must be 64 characters or fewer.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO users (user_id, display_name, custom_display_name)
               VALUES (?, ?, 1)
               ON CONFLICT(user_id) DO UPDATE SET
                   display_name = excluded.display_name,
                   custom_display_name = 1''',
            (user_id, cleaned),
        )
    _SYNCED_USERNAMES.pop(user_id, None)
    return cleaned


def load_afk_cache(conn=None):
    """Load active guild AFK entries from SQLite into memory."""
    global _AFK_CACHE_LOADED
    if conn is None:
        with get_db() as db_conn:
            rows = db_conn.execute(
                "SELECT guild_id, user_id, reason, since FROM guild_afk"
            ).fetchall()
    else:
        rows = conn.execute(
            "SELECT guild_id, user_id, reason, since FROM guild_afk"
        ).fetchall()

    fresh = {
        (guild_id, user_id): (reason, since)
        for guild_id, user_id, reason, since in rows
    }
    _AFK_CACHE.clear()
    _AFK_CACHE.update(fresh)
    _AFK_CACHE_LOADED = True


def _ensure_afk_cache_loaded():
    if not _AFK_CACHE_LOADED:
        load_afk_cache()


def set_guild_afk(guild_id, user_id, reason, since=None):
    """Persist a guild AFK status and update the in-memory cache."""
    since = time.time() if since is None else since
    with get_db() as conn:
        conn.execute(
            '''INSERT OR REPLACE INTO guild_afk
               (guild_id, user_id, reason, since)
               VALUES (?, ?, ?, ?)''',
            (guild_id, user_id, reason, since),
        )
    _AFK_CACHE[(guild_id, user_id)] = (reason, since)
    return since


def clear_guild_afk(guild_id, user_id):
    """Clear a guild AFK status if cached active; avoids SQLite on cache miss."""
    _ensure_afk_cache_loaded()
    key = (guild_id, user_id)
    if key not in _AFK_CACHE:
        return False

    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM guild_afk WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        )
        removed = cursor.rowcount > 0
    _AFK_CACHE.pop(key, None)
    return removed


def get_guild_afk_statuses(guild_id, user_ids):
    """Return [(user_id, reason, since)] for mentioned users from memory."""
    _ensure_afk_cache_loaded()
    statuses = []
    for user_id in user_ids:
        entry = _AFK_CACHE.get((guild_id, user_id))
        if entry is not None:
            statuses.append((user_id, entry[0], entry[1]))
    return statuses


# Database context manager for safer connections
@contextmanager
def get_db():
    conn = sqlite3.connect('kpop_cards.db', timeout=10.0)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# Database setup
def init_db():
    with get_db() as conn:
        conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
        c = conn.cursor()
        
        # Users table
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY, 
                      username TEXT, 
                      daily_streak INTEGER DEFAULT 0,
                      last_daily TEXT,
                      como INTEGER DEFAULT 0,
                      display_name TEXT,
                      custom_display_name INTEGER NOT NULL DEFAULT 0)''')
        
        # Cards table
        c.execute('''CREATE TABLE IF NOT EXISTS cards
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      serial TEXT UNIQUE,
                      member_code TEXT,
                      era TEXT,
                      rarity TEXT,
                      owner_id INTEGER,
                      obtained_at TEXT,
                      in_binder INTEGER NOT NULL DEFAULT 0,
                      FOREIGN KEY(owner_id) REFERENCES users(user_id))''')
        
        # Per-card skill points and training history
        c.execute('''CREATE TABLE IF NOT EXISTS card_skill_points
                     (card_serial TEXT PRIMARY KEY,
                      skill TEXT NOT NULL,
                      points INTEGER NOT NULL,
                      training_sessions INTEGER NOT NULL DEFAULT 0,
                      performances INTEGER NOT NULL DEFAULT 0,
                      last_trained REAL,
                      FOREIGN KEY(card_serial) REFERENCES cards(serial))''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_card_preferences
                     (user_id INTEGER NOT NULL,
                      action TEXT NOT NULL CHECK(action IN ('train', 'perform', 'hunt')),
                      card_serial TEXT NOT NULL,
                      PRIMARY KEY(user_id, action))''')

        # Cooldowns table
        c.execute('''CREATE TABLE IF NOT EXISTS cooldowns
                     (user_id INTEGER,
                      cooldown_type TEXT,
                      expires_at REAL,
                      PRIMARY KEY(user_id, cooldown_type))''')
        c.execute('''CREATE TABLE IF NOT EXISTS cooldown_reminders
                     (user_id INTEGER NOT NULL,
                      cooldown_type TEXT NOT NULL,
                      enabled INTEGER NOT NULL DEFAULT 0,
                      expires_at REAL,
                      PRIMARY KEY(user_id, cooldown_type))''')
        c.execute('''CREATE TABLE IF NOT EXISTS spin_usage
                     (user_id INTEGER PRIMARY KEY,
                      spin_date TEXT NOT NULL,
                      spins INTEGER NOT NULL DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS guild_afk
                     (guild_id INTEGER NOT NULL,
                      user_id INTEGER NOT NULL,
                      reason TEXT NOT NULL,
                      since REAL NOT NULL,
                      PRIMARY KEY(guild_id, user_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_drop_boosters
                     (user_id INTEGER PRIMARY KEY,
                      expires_at REAL NOT NULL,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_items
                     (user_id INTEGER NOT NULL,
                      item_key TEXT NOT NULL,
                      quantity INTEGER NOT NULL DEFAULT 0,
                      PRIMARY KEY(user_id, item_key),
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_item_effects
                     (user_id INTEGER PRIMARY KEY,
                      merge_discounts INTEGER NOT NULL DEFAULT 0,
                      streak_shields INTEGER NOT NULL DEFAULT 0,
                      extra_drop_slots INTEGER NOT NULL DEFAULT 0,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')

        c.execute('''CREATE TABLE IF NOT EXISTS user_targets
                     (user_id INTEGER PRIMARY KEY,
                      era TEXT,
                      member_code TEXT NOT NULL,
                      rarity TEXT,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS trivia_seen
                     (user_id INTEGER NOT NULL,
                      question_id TEXT NOT NULL,
                      difficulty TEXT NOT NULL,
                      seen_at TEXT NOT NULL,
                      PRIMARY KEY (user_id, question_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_biases
                     (user_id INTEGER NOT NULL,
                      member_code TEXT NOT NULL,
                      PRIMARY KEY(user_id, member_code),
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_bios
                     (user_id INTEGER PRIMARY KEY,
                      bio TEXT NOT NULL,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')
        
        # --- NEW: Market listings table ---
        c.execute('''CREATE TABLE IF NOT EXISTS market_listings
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      card_serial TEXT UNIQUE NOT NULL,
                      seller_id INTEGER NOT NULL,
                      price INTEGER NOT NULL,
                      listed_at TEXT NOT NULL,
                      FOREIGN KEY(card_serial) REFERENCES cards(serial),
                      FOREIGN KEY(seller_id) REFERENCES users(user_id))''')
        
        # Create indexes for better performance
        c.execute('''CREATE INDEX IF NOT EXISTS idx_cards_owner 
                     ON cards(owner_id)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_cards_serial 
                     ON cards(serial)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_cooldowns_expires 
                     ON cooldowns(expires_at)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_market_seller 
                     ON market_listings(seller_id)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_trivia_seen_user
                     ON trivia_seen(user_id, difficulty)''')
        
        # Check if columns exist, if not add them (for migration)
        c.execute("PRAGMA table_info(users)")
        user_columns = [column[1] for column in c.fetchall()]
        if 'display_name' not in user_columns:
            c.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
        if 'custom_display_name' not in user_columns:
            c.execute(
                "ALTER TABLE users ADD COLUMN custom_display_name "
                "INTEGER NOT NULL DEFAULT 0"
            )

        c.execute(
            '''SELECT sql FROM sqlite_master
               WHERE type='table' AND name='user_card_preferences' '''
        )
        pref_row = c.fetchone()
        if pref_row and "'hunt'" not in (pref_row[0] or ""):
            c.execute(
                '''CREATE TABLE user_card_preferences_new
                   (user_id INTEGER NOT NULL,
                    action TEXT NOT NULL CHECK(action IN ('train', 'perform', 'hunt')),
                    card_serial TEXT NOT NULL,
                    PRIMARY KEY(user_id, action))'''
            )
            c.execute(
                '''INSERT OR IGNORE INTO user_card_preferences_new
                   (user_id, action, card_serial)
                   SELECT user_id, action, card_serial
                   FROM user_card_preferences'''
            )
            c.execute("DROP TABLE user_card_preferences")
            c.execute(
                "ALTER TABLE user_card_preferences_new RENAME TO user_card_preferences"
            )

        c.execute("PRAGMA table_info(cards)")
        columns = [column[1] for column in c.fetchall()]
        if 'era' not in columns:
            c.execute("ALTER TABLE cards ADD COLUMN era TEXT")
            c.execute("UPDATE cards SET era = 'AAA' WHERE era IS NULL")
        if 'in_binder' not in columns:
            c.execute(
                "ALTER TABLE cards ADD COLUMN in_binder "
                "INTEGER NOT NULL DEFAULT 0"
            )
        c.execute('''CREATE INDEX IF NOT EXISTS idx_cards_binder
                     ON cards(owner_id, in_binder)''')
        load_afk_cache(conn)

init_db()
