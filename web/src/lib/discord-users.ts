import fs from "node:fs";
import path from "node:path";
import {
  formatFallbackDisplayName,
  getStoredDisplayName,
  isPlaceholderUsername,
  isSyntheticUserId,
} from "./player-names";

export {
  formatFallbackDisplayName,
  getStoredDisplayName,
  isPlaceholderUsername,
  isSyntheticUserId,
};

export interface DiscordUserInfo {
  userId: string;
  displayName: string;
  username: string;
  globalName: string | null;
  avatar: string | null;
  avatarUrl: string | null;
}

interface CachedEntry {
  displayName: string | null;
  username: string | null;
  globalName: string | null;
  avatar: string | null;
  fetchedAt: number;
  notFound?: boolean;
}

interface CacheState {
  entries: Map<string, CachedEntry>;
  transientFailures: Map<string, number>;
  inFlight: Map<string, Promise<DiscordUserInfo | null>>;
  diskLoaded: boolean;
  rateLimitedUntil: number;
  authFailedUntil: number;
  authWarned: boolean;
}

const TTL_MS = 24 * 60 * 60 * 1000;
const TRANSIENT_FAILURE_TTL_MS = 60 * 1000;
const AUTH_FAILURE_TTL_MS = 5 * 60 * 1000;
const DEFAULT_MAX_LIVE_FETCHES = 25;
const FETCH_CONCURRENCY = 4;
const SNOWFLAKE_RE = /^\d{15,22}$/;

const CACHE_FILE_PATH = path.resolve(
  process.cwd(),
  ".cache",
  "discord-users.json"
);

const globalForDiscordCache = globalThis as typeof globalThis & {
  __kotoneDiscordUserCache?: CacheState;
};

function getCacheState(): CacheState {
  if (!globalForDiscordCache.__kotoneDiscordUserCache) {
    globalForDiscordCache.__kotoneDiscordUserCache = {
      entries: new Map(),
      transientFailures: new Map(),
      inFlight: new Map(),
      diskLoaded: false,
      rateLimitedUntil: 0,
      authFailedUntil: 0,
      authWarned: false,
    };
  }
  return globalForDiscordCache.__kotoneDiscordUserCache;
}

export function buildDiscordAvatarUrl(
  userId: string,
  avatarHash: string | null | undefined,
  size = 128
): string | null {
  if (!avatarHash) return null;
  const ext = avatarHash.startsWith("a_") ? "gif" : "png";
  return `https://cdn.discordapp.com/avatars/${userId}/${avatarHash}.${ext}?size=${size}`;
}

function entryToUserInfo(
  userId: string,
  entry: CachedEntry
): DiscordUserInfo | null {
  if (entry.notFound || !entry.displayName || !entry.username) {
    return null;
  }
  return {
    userId,
    displayName: entry.displayName,
    username: entry.username,
    globalName: entry.globalName,
    avatar: entry.avatar,
    avatarUrl: buildDiscordAvatarUrl(userId, entry.avatar),
  };
}

function ensureDiskCacheLoaded(state: CacheState): void {
  if (state.diskLoaded) return;
  state.diskLoaded = true;
  try {
    if (!fs.existsSync(CACHE_FILE_PATH)) return;
    const raw = fs.readFileSync(CACHE_FILE_PATH, "utf8");
    const parsed = JSON.parse(raw) as Record<string, CachedEntry>;
    if (!parsed || typeof parsed !== "object") return;
    const now = Date.now();
    for (const [id, entry] of Object.entries(parsed)) {
      if (
        SNOWFLAKE_RE.test(id) &&
        entry &&
        typeof entry === "object" &&
        typeof entry.fetchedAt === "number" &&
        now - entry.fetchedAt < TTL_MS
      ) {
        state.entries.set(id, entry);
      }
    }
  } catch {
    // Ignore missing or corrupted cache file.
  }
}

function flushDiskCache(state: CacheState): void {
  try {
    const dir = path.dirname(CACHE_FILE_PATH);
    fs.mkdirSync(dir, { recursive: true });
    const now = Date.now();
    const serializable: Record<string, CachedEntry> = {};
    for (const [id, entry] of state.entries.entries()) {
      if (now - entry.fetchedAt < TTL_MS) {
        serializable[id] = entry;
      } else {
        state.entries.delete(id);
      }
    }
    const payload = JSON.stringify(serializable, null, 2);
    const tmpPath = `${CACHE_FILE_PATH}.${process.pid}.${Date.now()}.tmp`;
    try {
      fs.writeFileSync(tmpPath, payload, "utf8");
      fs.renameSync(tmpPath, CACHE_FILE_PATH);
    } catch {
      try {
        if (fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath);
      } catch {
        // Ignore cleanup failure.
      }
      fs.writeFileSync(CACHE_FILE_PATH, payload, "utf8");
    }
  } catch {
    // Disk cache persistence is best-effort only.
  }
}

function getFreshCachedEntry(
  state: CacheState,
  userId: string,
  now = Date.now()
): CachedEntry | null {
  const entry = state.entries.get(userId);
  if (!entry) return null;
  if (now - entry.fetchedAt >= TTL_MS) {
    state.entries.delete(userId);
    return null;
  }
  return entry;
}

function getBotToken(): string | null {
  const token = process.env.DISCORD_BOT_TOKEN?.trim();
  return token ? token : null;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchDiscordUserFromApi(
  userId: string,
  state: CacheState,
  token: string,
  allowRetry = true
): Promise<{ result: DiscordUserInfo | null; cacheDirty: boolean }> {
  const now = Date.now();
  if (now < state.rateLimitedUntil || now < state.authFailedUntil) {
    return { result: null, cacheDirty: false };
  }

  try {
    const response = await fetch(
      `https://discord.com/api/v10/users/${userId}`,
      {
        headers: {
          Authorization: `Bot ${token}`,
        },
        cache: "no-store",
        signal: AbortSignal.timeout(5000),
      }
    );

    const remaining = response.headers.get("x-ratelimit-remaining");
    const resetAfterHeader = response.headers.get("x-ratelimit-reset-after");
    if (remaining === "0" && resetAfterHeader) {
      const resetSec = Number(resetAfterHeader);
      if (Number.isFinite(resetSec) && resetSec > 0) {
        state.rateLimitedUntil = Math.max(
          state.rateLimitedUntil,
          Date.now() + Math.ceil(resetSec * 1000)
        );
      }
    }

    if (response.status === 429) {
      let retryAfterSec = Number(response.headers.get("retry-after") ?? "");
      if (!Number.isFinite(retryAfterSec) || retryAfterSec <= 0) {
        try {
          const body = (await response.json()) as { retry_after?: number };
          if (typeof body?.retry_after === "number" && body.retry_after > 0) {
            retryAfterSec = body.retry_after;
          }
        } catch {
          // Ignore JSON parse errors on 429 body.
        }
      }
      if (!Number.isFinite(retryAfterSec) || retryAfterSec <= 0) {
        retryAfterSec = 5;
      }

      if (allowRetry && retryAfterSec <= 2) {
        await sleep(Math.ceil(retryAfterSec * 1000));
        return fetchDiscordUserFromApi(userId, state, token, false);
      }

      state.rateLimitedUntil = Math.max(
        state.rateLimitedUntil,
        Date.now() + Math.ceil(retryAfterSec * 1000)
      );
      return { result: null, cacheDirty: false };
    }

    if (response.status === 401 || response.status === 403) {
      state.authFailedUntil = Date.now() + AUTH_FAILURE_TTL_MS;
      if (!state.authWarned) {
        state.authWarned = true;
        console.warn(
          `[discord-users] Discord API returned ${response.status}; verify DISCORD_BOT_TOKEN in web/.env.local.`
        );
      }
      return { result: null, cacheDirty: false };
    }

    if (response.status === 404) {
      state.entries.set(userId, {
        displayName: null,
        username: null,
        globalName: null,
        avatar: null,
        fetchedAt: Date.now(),
        notFound: true,
      });
      return { result: null, cacheDirty: true };
    }

    if (!response.ok) {
      state.transientFailures.set(
        userId,
        Date.now() + TRANSIENT_FAILURE_TTL_MS
      );
      return { result: null, cacheDirty: false };
    }

    const data = (await response.json()) as {
      id?: string;
      username?: string;
      global_name?: string | null;
      avatar?: string | null;
    };

    const username = data.username?.trim() || "";
    const globalName = data.global_name?.trim() || null;
    const displayName = globalName || username;
    const avatar = data.avatar ?? null;

    if (!displayName || !username) {
      state.transientFailures.set(
        userId,
        Date.now() + TRANSIENT_FAILURE_TTL_MS
      );
      return { result: null, cacheDirty: false };
    }

    const entry: CachedEntry = {
      displayName,
      username,
      globalName,
      avatar,
      fetchedAt: Date.now(),
    };
    state.entries.set(userId, entry);
    state.transientFailures.delete(userId);
    return { result: entryToUserInfo(userId, entry), cacheDirty: true };
  } catch {
    state.transientFailures.set(userId, Date.now() + TRANSIENT_FAILURE_TTL_MS);
    return { result: null, cacheDirty: false };
  }
}

export async function resolveDiscordUser(
  userId: string
): Promise<DiscordUserInfo | null> {
  const trimmed = userId.trim();
  if (!SNOWFLAKE_RE.test(trimmed) || isSyntheticUserId(trimmed)) return null;

  const state = getCacheState();
  ensureDiskCacheLoaded(state);

  const now = Date.now();
  const cached = getFreshCachedEntry(state, trimmed, now);
  if (cached) {
    return entryToUserInfo(trimmed, cached);
  }

  const token = getBotToken();
  if (!token) return null;

  const failedUntil = state.transientFailures.get(trimmed);
  if (failedUntil && failedUntil > now) {
    return null;
  }

  const existingInFlight = state.inFlight.get(trimmed);
  if (existingInFlight) {
    return existingInFlight;
  }

  const promise = (async () => {
    const { result, cacheDirty } = await fetchDiscordUserFromApi(
      trimmed,
      state,
      token
    );
    if (cacheDirty) {
      flushDiskCache(state);
    }
    return result;
  })().finally(() => {
    state.inFlight.delete(trimmed);
  });

  state.inFlight.set(trimmed, promise);
  return promise;
}

export async function resolveDiscordUsers(
  userIds: string[],
  options?: { priorityIds?: Iterable<string>; maxLiveFetches?: number }
): Promise<Map<string, DiscordUserInfo>> {
  const results = new Map<string, DiscordUserInfo>();
  const uniqueIds: string[] = [];
  const seen = new Set<string>();

  for (const rawId of userIds) {
    const id = rawId.trim();
    if (!SNOWFLAKE_RE.test(id) || isSyntheticUserId(id) || seen.has(id)) {
      continue;
    }
    seen.add(id);
    uniqueIds.push(id);
  }

  if (uniqueIds.length === 0) return results;

  const state = getCacheState();
  ensureDiskCacheLoaded(state);

  const now = Date.now();
  const uncachedIds: string[] = [];

  for (const id of uniqueIds) {
    const cached = getFreshCachedEntry(state, id, now);
    if (cached) {
      const info = entryToUserInfo(id, cached);
      if (info) results.set(id, info);
      continue;
    }

    const failedUntil = state.transientFailures.get(id);
    if (failedUntil && failedUntil > now) {
      continue;
    }

    uncachedIds.push(id);
  }

  const token = getBotToken();
  if (!token || uncachedIds.length === 0) {
    return results;
  }

  const prioritySet = new Set(
    Array.from(options?.priorityIds ?? []).map((id) => id.trim())
  );
  uncachedIds.sort((a, b) => {
    const aPri = prioritySet.has(a) ? 0 : 1;
    const bPri = prioritySet.has(b) ? 0 : 1;
    return aPri - bPri;
  });

  const maxLiveFetches = Math.max(
    0,
    options?.maxLiveFetches ?? DEFAULT_MAX_LIVE_FETCHES
  );
  const toFetch = uncachedIds.slice(0, maxLiveFetches);

  let cursor = 0;
  let dirty = false;

  async function worker() {
    while (cursor < toFetch.length) {
      const currentNow = Date.now();
      if (
        currentNow < state.rateLimitedUntil ||
        currentNow < state.authFailedUntil
      ) {
        break;
      }

      const id = toFetch[cursor++];
      const inFlight = state.inFlight.get(id);
      if (inFlight) {
        const info = await inFlight;
        if (info) results.set(id, info);
        continue;
      }

      const promise = (async () => {
        const { result, cacheDirty } = await fetchDiscordUserFromApi(
          id,
          state,
          token!
        );
        if (cacheDirty) dirty = true;
        return result;
      })().finally(() => {
        state.inFlight.delete(id);
      });

      state.inFlight.set(id, promise);
      const info = await promise;
      if (info) results.set(id, info);
    }
  }

  const workerCount = Math.min(FETCH_CONCURRENCY, toFetch.length);
  await Promise.all(Array.from({ length: workerCount }, () => worker()));

  if (dirty) {
    flushDiskCache(state);
  }

  return results;
}
