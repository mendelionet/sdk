import { chmodSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

/** What `mendelio-voice login` writes and the client reads back. Never contains a hash — only the key. */
export interface Credentials {
  api_key: string;
  key_prefix: string;
  created_at: string;
}

function credentialsPath(): string {
  const base = process.env.XDG_CONFIG_HOME || join(homedir(), ".config");
  return join(base, "mendelio", "credentials.json");
}

/** Read stored credentials, or undefined if none / unreadable. Never throws. */
export function readCredentials(): Credentials | undefined {
  try {
    const raw = readFileSync(credentialsPath(), "utf8");
    const parsed = JSON.parse(raw) as Partial<Credentials>;
    return typeof parsed?.api_key === "string" &&
      parsed.api_key.length > 0 &&
      typeof parsed.key_prefix === "string" &&
      typeof parsed.created_at === "string"
      ? parsed as Credentials
      : undefined;
  } catch {
    return undefined;
  }
}

/** Write credentials with owner-only permissions (a secret in a world-readable file is a leak). */
export function writeCredentials(credentials: Credentials): void {
  const path = credentialsPath();
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(credentials, null, 2), { mode: 0o600 });
  try {
    chmodSync(path, 0o600);
  } catch {
    // best-effort on platforms without POSIX modes
  }
}

/** Remove stored credentials (`logout`). No-op if absent. */
export function clearCredentials(): void {
  try {
    rmSync(credentialsPath());
  } catch {
    // already gone
  }
}
