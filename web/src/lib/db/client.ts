import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

const globalForDb = globalThis as typeof globalThis & {
  __kotoneDb?: DatabaseSync;
  __kotoneDbPath?: string;
  __kotoneHasDisplayNameCol?: boolean;
};

export function resolveDatabasePath(): string {
  const configured = process.env.DATABASE_PATH?.trim() || "../kpop_cards.db";
  return path.isAbsolute(configured)
    ? configured
    : path.resolve(process.cwd(), configured);
}

/**
 * Strictly read-only SQLite connection to the shared bot database.
 * Uses `readBigInts: true` so 64-bit Discord Snowflake IDs never lose precision.
 */
export function getReadOnlyDb(): DatabaseSync {
  const dbPath = resolveDatabasePath();

  if (globalForDb.__kotoneDb && globalForDb.__kotoneDbPath === dbPath) {
    return globalForDb.__kotoneDb;
  }

  if (globalForDb.__kotoneDb && globalForDb.__kotoneDbPath !== dbPath) {
    try {
      globalForDb.__kotoneDb.close();
    } catch {
      // Ignore close errors when switching database paths.
    }
    globalForDb.__kotoneDb = undefined;
    globalForDb.__kotoneDbPath = undefined;
    globalForDb.__kotoneHasDisplayNameCol = undefined;
  }

  if (!fs.existsSync(dbPath)) {
    throw new Error(
      `Shared SQLite database not found at "${dbPath}". Check DATABASE_PATH in .env.local.`
    );
  }

  const db = new DatabaseSync(dbPath, {
    readOnly: true,
    readBigInts: true,
    timeout: 10000,
  });

  globalForDb.__kotoneDb = db;
  globalForDb.__kotoneDbPath = dbPath;

  return db;
}

export function hasUsersDisplayNameColumn(db: DatabaseSync): boolean {
  if (globalForDb.__kotoneHasDisplayNameCol) {
    return true;
  }
  try {
    const columns = db
      .prepare("PRAGMA table_info(users)")
      .all() as Array<{ name: string }>;
    const exists = columns.some((col) => col.name === "display_name");
    if (exists) {
      globalForDb.__kotoneHasDisplayNameCol = true;
    }
    return exists;
  } catch {
    return false;
  }
}

export function parseSnowflake(value: string | null | undefined): bigint | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!/^\d{15,22}$/.test(trimmed)) {
    return null;
  }
  try {
    return BigInt(trimmed);
  } catch {
    return null;
  }
}

export function toSnowflakeString(
  value: bigint | number | string | null | undefined
): string {
  if (value === null || value === undefined) return "";
  return typeof value === "bigint" ? value.toString() : String(value);
}

export function toInt(value: bigint | number | null | undefined): number {
  if (value === null || value === undefined) return 0;
  return typeof value === "bigint" ? Number(value) : Number(value);
}
