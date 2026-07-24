import { WebhookVerificationError } from "./errors.js";
import type { WebhookEvent, WebhookEventType } from "./types.js";

/**
 * Webhook verification. The server signs `"{timestamp}.{rawBody}"` with HMAC-SHA256 under your
 * endpoint secret and sends `Voice-Signature: t=<ts>,v1=<hex>` plus `Voice-Timestamp`. Verify against
 * the RAW request body (not a re-serialized object — key order would differ and the HMAC would fail).
 */
export interface VerifyOptions {
  toleranceSec?: number;
  /** Injectable clock for tests. Milliseconds. */
  now?: number;
}

type HeaderBag = Record<string, string | string[] | undefined> | Headers;

function header(headers: HeaderBag, name: string): string | undefined {
  if (headers instanceof Headers) return headers.get(name) ?? undefined;
  const lower = name.toLowerCase();
  for (const [k, v] of Object.entries(headers)) {
    if (k.toLowerCase() === lower) return Array.isArray(v) ? v[0] : v;
  }
  return undefined;
}

function parseSignature(value: string): { t: number; v1: string } | null {
  let t: number | undefined;
  let v1: string | undefined;
  for (const part of value.split(",")) {
    const [k, val] = part.split("=", 2);
    if (k === "t" && val) t = Number(val);
    if (k === "v1" && val) v1 = val;
  }
  if (t === undefined || !Number.isFinite(t) || !v1) return null;
  return { t, v1 };
}

async function hmacHex(secret: string, message: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Constant-time hex string comparison. */
function timingSafeEqualHex(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Verify a webhook signature. Returns true/false; never throws. */
export async function verifySignature(
  rawBody: string,
  headers: HeaderBag,
  secret: string,
  options: VerifyOptions = {},
): Promise<boolean> {
  const sigHeader = header(headers, "Voice-Signature");
  const timestampHeader = header(headers, "Voice-Timestamp");
  if (!sigHeader || !timestampHeader) return false;
  const parsed = parseSignature(sigHeader);
  if (!parsed) return false;
  const headerTimestamp = Number(timestampHeader);
  if (!Number.isFinite(headerTimestamp) || headerTimestamp !== parsed.t) return false;

  const toleranceSec = options.toleranceSec ?? 300;
  const nowSec = Math.floor((options.now ?? Date.now()) / 1000);
  if (Math.abs(nowSec - parsed.t) > toleranceSec) return false;

  const expected = await hmacHex(secret, `${parsed.t}.${rawBody}`);
  return timingSafeEqualHex(expected, parsed.v1);
}

const EVENT_TYPES = new Set<WebhookEventType>([
  "speech_job.completed",
  "speech_job.failed",
  "speech_job.cancelled",
  "voice.ready",
  "voice.failed",
  "transcription.completed",
  "transcription.failed",
  "transcription.expired",
]);

/**
 * Verify AND parse a webhook into a typed event, or throw WebhookVerificationError. Deduplicate by
 * `event.id` — deliveries are at-least-once.
 */
export async function constructEvent(
  rawBody: string,
  headers: HeaderBag,
  secret: string,
  options: VerifyOptions = {},
): Promise<WebhookEvent> {
  if (!(await verifySignature(rawBody, headers, secret, options))) {
    throw new WebhookVerificationError("Webhook signature verification failed.");
  }
  let parsed: WebhookEvent;
  try {
    parsed = JSON.parse(rawBody) as WebhookEvent;
  } catch {
    throw new WebhookVerificationError("Webhook body is not valid JSON.");
  }
  if (!parsed || !EVENT_TYPES.has(parsed.type)) {
    throw new WebhookVerificationError(`Unknown webhook event type: ${String(parsed?.type)}.`);
  }
  return parsed;
}
