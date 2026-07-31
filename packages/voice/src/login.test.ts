import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readCredentials } from "./credentials.js";
import { deviceLogin, MENDELIO_VOICE_CLI_CLIENT_ID } from "./login.js";

const originalConfigHome = process.env.XDG_CONFIG_HOME;

afterEach(() => {
  vi.useRealTimers();
  if (originalConfigHome === undefined) delete process.env.XDG_CONFIG_HOME;
  else process.env.XDG_CONFIG_HOME = originalConfigHome;
});

describe("deviceLogin", () => {
  it("surfaces the code, respects slow_down, and persists an approved key", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-24T08:00:00.000Z"));
    process.env.XDG_CONFIG_HOME = mkdtempSync(join(tmpdir(), "mendelio-login-test-"));
    const responses = [
      new Response(JSON.stringify({
        issuer: "https://api.example",
        device_authorization_endpoint: "https://api.example/oauth/device/code",
        token_endpoint: "https://api.example/oauth/token",
      }), { status: 200 }),
      new Response(JSON.stringify({
        device_code: "device-secret",
        user_code: "ABCD-EFGH",
        verification_uri: "https://voice.example/activate",
        verification_uri_complete: "https://voice.example/activate?code=ABCD-EFGH",
        expires_in: 60,
        interval: 1,
      }), { status: 200 }),
      new Response(JSON.stringify({ error: "authorization_pending" }), { status: 400 }),
      new Response(JSON.stringify({ error: "slow_down" }), { status: 400 }),
      new Response(JSON.stringify({ access_token: "mvo_approved_test_key" }), { status: 200 }),
    ];
    const requests: { url: string; init: RequestInit | undefined }[] = [];
    const fetch = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      requests.push({ url: String(input), init });
      const response = responses.shift();
      if (!response) throw new Error("Unexpected device-login request");
      return response;
    }) as unknown as typeof globalThis.fetch;
    const onCode = vi.fn();

    const login = deviceLogin({
      apiBaseUrl: "https://api.example/",
      openBrowser: false,
      fetch,
      onCode,
    });
    await vi.advanceTimersByTimeAsync(1_000);
    await vi.advanceTimersByTimeAsync(1_000);
    await vi.advanceTimersByTimeAsync(6_000);

    await expect(login).resolves.toEqual({ keyPrefix: "mvo_approved" });
    expect(onCode).toHaveBeenCalledWith({
      userCode: "ABCD-EFGH",
      verificationUri: "https://voice.example/activate",
      verificationUriComplete: "https://voice.example/activate?code=ABCD-EFGH",
    });
    expect(requests.map((request) => request.url)).toEqual([
      "https://api.example/.well-known/oauth-authorization-server",
      "https://api.example/oauth/device/code",
      "https://api.example/oauth/token",
      "https://api.example/oauth/token",
      "https://api.example/oauth/token",
    ]);
    expect(requests[1]?.init?.headers).toEqual({ "content-type": "application/x-www-form-urlencoded" });
    expect(String(requests[1]?.init?.body)).toContain("label=");
    expect(String(requests[1]?.init?.body)).toContain(`client_id=${MENDELIO_VOICE_CLI_CLIENT_ID}`);
    const tokenBody = requests[2]?.init?.body;
    expect(String(tokenBody)).toContain("device_code=device-secret");
    expect(String(tokenBody)).toContain(`client_id=${MENDELIO_VOICE_CLI_CLIENT_ID}`);
    expect(readCredentials()).toMatchObject({
      api_key: "mvo_approved_test_key",
      key_prefix: "mvo_approved",
    });
  });
});
