import { mkdirSync, mkdtempSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { clearCredentials, readCredentials, writeCredentials } from "./credentials.js";

const originalConfigHome = process.env.XDG_CONFIG_HOME;

afterEach(() => {
  if (originalConfigHome === undefined) delete process.env.XDG_CONFIG_HOME;
  else process.env.XDG_CONFIG_HOME = originalConfigHome;
});

function isolatedCredentialPath(): string {
  const configHome = mkdtempSync(join(tmpdir(), "mendelio-credentials-test-"));
  process.env.XDG_CONFIG_HOME = configHome;
  return join(configHome, "mendelio", "credentials.json");
}

describe("credential persistence", () => {
  it("round-trips credentials with owner-only file permissions", () => {
    const path = isolatedCredentialPath();
    const credentials = {
      api_key: "mv_live_test",
      key_prefix: "mv_live_test",
      created_at: "2026-07-24T00:00:00.000Z",
    };

    writeCredentials(credentials);

    expect(readCredentials()).toEqual(credentials);
    expect(statSync(path).mode & 0o777).toBe(0o600);

    clearCredentials();
    expect(readCredentials()).toBeUndefined();
  });

  it("rejects malformed and structurally incomplete credential files", () => {
    const path = isolatedCredentialPath();
    mkdirSync(dirname(path), { recursive: true });

    writeFileSync(path, "{not-json", "utf8");
    expect(readCredentials()).toBeUndefined();

    writeFileSync(path, JSON.stringify({ api_key: "mv_live_test" }), "utf8");
    expect(readCredentials()).toBeUndefined();
  });
});
