const PLACEHOLDER_USERNAME_RE = /^user_\d+$/i;
const SYNTHETIC_COLLECTOR_RE = /^900000000000000(\d{3,})$/;

export function isPlaceholderUsername(
  username: string | null | undefined
): boolean {
  if (!username) return true;
  const trimmed = username.trim();
  if (!trimmed) return true;
  if (PLACEHOLDER_USERNAME_RE.test(trimmed)) return true;
  return /^(unknown|unknown user)$/i.test(trimmed);
}

export function isSyntheticUserId(userId: string): boolean {
  return SYNTHETIC_COLLECTOR_RE.test(userId.trim());
}

export function formatFallbackDisplayName(userId: string): string {
  const trimmed = userId.trim();
  const match = SYNTHETIC_COLLECTOR_RE.exec(trimmed);
  if (match) {
    return `Collector #${match[1]}`;
  }
  return `user_${trimmed.slice(-4)}`;
}

export function getStoredDisplayName(
  dbDisplayName: string | null | undefined,
  dbUsername: string | null | undefined
): string | null {
  if (dbDisplayName && !isPlaceholderUsername(dbDisplayName)) {
    return dbDisplayName.trim();
  }
  if (dbUsername && !isPlaceholderUsername(dbUsername)) {
    return dbUsername.trim();
  }
  return null;
}
