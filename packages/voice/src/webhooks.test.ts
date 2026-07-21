import { describe, expect, it } from "vitest";
import { constructEvent, verifySignature } from "./webhooks.js";
import { WebhookVerificationError } from "./errors.js";

const SECRET = "whsec_test_secret";

async function sign(body: string, t: number, secret = SECRET): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`${t}.${body}`));
  const hex = Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, "0")).join("");
  return `t=${t},v1=${hex}`;
}

const NOW = 1_753_000_000_000; // fixed clock (ms)
const T = Math.floor(NOW / 1000);
const BODY = JSON.stringify({ id: "evt_1", type: "generation.completed", created: T, data: { id: "gen_1" } });

describe("verifySignature", () => {
  it("accepts a valid signature over the raw body", async () => {
    const headers = { "Voice-Signature": await sign(BODY, T), "Voice-Timestamp": String(T) };
    expect(await verifySignature(BODY, headers, SECRET, { now: NOW })).toBe(true);
  });

  it("is case-insensitive about header names", async () => {
    const headers = { "voice-signature": await sign(BODY, T) };
    expect(await verifySignature(BODY, headers, SECRET, { now: NOW })).toBe(true);
  });

  it("rejects a tampered body", async () => {
    const headers = { "Voice-Signature": await sign(BODY, T) };
    expect(await verifySignature(BODY + " ", headers, SECRET, { now: NOW })).toBe(false);
  });

  it("rejects a wrong secret", async () => {
    const headers = { "Voice-Signature": await sign(BODY, T, "whsec_other") };
    expect(await verifySignature(BODY, headers, SECRET, { now: NOW })).toBe(false);
  });

  it("rejects a timestamp outside tolerance", async () => {
    const old = T - 10_000;
    const headers = { "Voice-Signature": await sign(BODY, old) };
    expect(await verifySignature(BODY, headers, SECRET, { now: NOW })).toBe(false);
  });

  it("rejects a missing signature header", async () => {
    expect(await verifySignature(BODY, {}, SECRET, { now: NOW })).toBe(false);
  });
});

describe("constructEvent", () => {
  it("returns the typed event on a valid signature", async () => {
    const headers = { "Voice-Signature": await sign(BODY, T) };
    const event = await constructEvent(BODY, headers, SECRET, { now: NOW });
    expect(event.type).toBe("generation.completed");
    expect(event.id).toBe("evt_1");
  });

  it("throws WebhookVerificationError on a bad signature", async () => {
    await expect(constructEvent(BODY, { "Voice-Signature": "t=1,v1=deadbeef" }, SECRET, { now: NOW }))
      .rejects.toBeInstanceOf(WebhookVerificationError);
  });

  it("throws on an unknown event type", async () => {
    const body = JSON.stringify({ id: "x", type: "nope", created: T, data: {} });
    const headers = { "Voice-Signature": await sign(body, T) };
    await expect(constructEvent(body, headers, SECRET, { now: NOW }))
      .rejects.toBeInstanceOf(WebhookVerificationError);
  });
});
