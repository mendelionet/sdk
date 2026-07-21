import { describe, expect, it, vi } from "vitest";
import { MendelioVoice } from "./client.js";
import {
  AuthenticationError,
  CapacityError,
  GenerationFailedError,
  IdempotencyError,
  InvalidRequestError,
  PermissionError,
} from "./errors.js";

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}
function envelope(type: string, code: string, param: string | null = null) {
  return { error: { type, code, message: `${code} message`, param, request_id: "req_test" } };
}

/** A fetch that returns queued responses in order and records the requests it saw. */
function queuedFetch(responses: Response[]): { fetch: typeof fetch; calls: Request[] } {
  const calls: Request[] = [];
  const fetchImpl = (async (input: any, init?: any) => {
    calls.push(new Request(typeof input === "string" ? input : input.toString(), init));
    const next = responses.shift();
    if (!next) throw new Error("no more queued responses");
    return next;
  }) as unknown as typeof fetch;
  return { fetch: fetchImpl, calls };
}

const KEY = "mv_live_testkey";

describe("error mapping", () => {
  it.each([
    [401, "authentication_error", "authentication_required", AuthenticationError],
    [403, "permission_error", "permission_denied", PermissionError],
    [400, "invalid_request_error", "invalid_request", InvalidRequestError],
    [402, "invalid_request_error", "insufficient_credit", InvalidRequestError],
    [409, "idempotency_error", "idempotency_conflict", IdempotencyError],
    [429, "capacity_error", "capacity_saturated", CapacityError],
  ])("maps %s → the right subclass", async (status, type, code, Ctor) => {
    const { fetch } = queuedFetch([json(status as number, envelope(type as string, code as string))]);
    const client = new MendelioVoice({ apiKey: KEY, fetch, maxRetries: 0 });
    await expect(client.models.list()).rejects.toBeInstanceOf(Ctor as any);
  });

  it("carries code, param and requestId", async () => {
    const { fetch } = queuedFetch([json(400, envelope("invalid_request_error", "invalid_request", "text"))]);
    const client = new MendelioVoice({ apiKey: KEY, fetch, maxRetries: 0 });
    let err: InvalidRequestError | undefined;
    try {
      await client.models.list();
    } catch (e) {
      err = e as InvalidRequestError;
    }
    expect(err?.code).toBe("invalid_request");
    expect(err?.param).toBe("text");
    expect(err?.requestId).toBe("req_test");
  });
});

describe("auth key resolution", () => {
  it("throws AuthenticationError at first request with no key", async () => {
    const { fetch } = queuedFetch([json(200, {})]);
    const prev = process.env.MENDELIO_VOICE_API_KEY;
    delete process.env.MENDELIO_VOICE_API_KEY;
    const client = new MendelioVoice({ fetch, baseUrl: "https://api.example/v1/voice" });
    await expect(client.balance.get()).rejects.toBeInstanceOf(AuthenticationError);
    if (prev) process.env.MENDELIO_VOICE_API_KEY = prev;
  });
});

describe("retry", () => {
  it("retries GET on 429 respecting Retry-After, then succeeds", async () => {
    const { fetch, calls } = queuedFetch([
      json(429, envelope("capacity_error", "capacity_saturated"), { "retry-after": "0" }),
      json(200, { object: "voice.list", data: [], has_more: false, next_cursor: null }),
    ]);
    const client = new MendelioVoice({ apiKey: KEY, fetch, maxRetries: 2 });
    await client.models.list();
    expect(calls).toHaveLength(2);
  });

  it("does not retry a 400", async () => {
    const { fetch, calls } = queuedFetch([json(400, envelope("invalid_request_error", "invalid_request"))]);
    const client = new MendelioVoice({ apiKey: KEY, fetch, maxRetries: 3 });
    await expect(client.models.list()).rejects.toBeInstanceOf(InvalidRequestError);
    expect(calls).toHaveLength(1);
  });

  it("reuses one idempotency key across retries of a create", async () => {
    const { fetch, calls } = queuedFetch([
      json(500, envelope("api_error", "internal_error")),
      json(200, { id: "gen_1", object: "voice.generation", state: "queued", cost: { unit: "audio_second", status: "reserved", estimated: 1, reserved: 1 } }),
    ]);
    const client = new MendelioVoice({ apiKey: KEY, fetch, maxRetries: 2 });
    await client.generations.create({ text: "Ahoj", voiceVersionId: "v1" });
    expect(calls).toHaveLength(2);
    const k0 = calls[0]!.headers.get("idempotency-key");
    const k1 = calls[1]!.headers.get("idempotency-key");
    expect(k0).toBeTruthy();
    expect(k0).toBe(k1);
  });
});

describe("generations.waitFor", () => {
  it("polls until completed", async () => {
    const gen = (state: string) => json(200, { id: "g", object: "voice.generation", state, cost: { unit: "audio_second", status: "reserved", estimated: 1, reserved: 1 } });
    const { fetch } = queuedFetch([gen("queued"), gen("generating"), gen("completed")]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });
    const result = await client.generations.waitFor("g", { pollIntervalMs: 1 });
    expect(result.state).toBe("completed");
  });

  it("throws GenerationFailedError on failed", async () => {
    const { fetch } = queuedFetch([json(200, { id: "g", object: "voice.generation", state: "failed", cost: { unit: "audio_second", status: "reserved", estimated: 1, reserved: 1 } })]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });
    await expect(client.generations.waitFor("g", { pollIntervalMs: 1 })).rejects.toBeInstanceOf(GenerationFailedError);
  });
});

describe("generations.download", () => {
  it("re-fetches for a fresh URL when the cached output is expired", async () => {
    const globalFetch = vi.spyOn(globalThis, "fetch");
    globalFetch.mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3])));
    const { fetch } = queuedFetch([
      json(200, {
        id: "g", object: "voice.generation", state: "completed",
        cost: { unit: "audio_second", status: "final", reserved: 1, consumed: 1, refunded: 0 },
        output: { status: "available", format: "mp3", audio_seconds: 1, bytes: 3, sha256: "a".repeat(64), retention_expires_at: "x", url: "https://dl/fresh", url_expires_at: "y" },
      }),
    ]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });
    const audio = await client.generations.download({ id: "g", object: "voice.generation", state: "completed", cost: { unit: "audio_second", status: "final", reserved: 1, consumed: 1, refunded: 0 }, output: { status: "expired", format: "mp3", retention_expires_at: "x" } });
    expect(Array.from(audio)).toEqual([1, 2, 3]);
    globalFetch.mockRestore();
  });
});

describe("voices pagination + speak", () => {
  it("iterates across pages", async () => {
    const voice = (id: string, kind?: string) => ({ id, object: "voice.voice", voice_profile_id: "p", name: id, language: "cs", state: "ready", failure_code: null, created_at: "x", ready_at: "x", languages: [], ...(kind ? { kind } : {}) });
    const { fetch } = queuedFetch([
      json(200, { object: "voice.list", data: [voice("v1")], has_more: true, next_cursor: "c1" }),
      json(200, { object: "voice.list", data: [voice("v2")], has_more: false, next_cursor: null }),
    ]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });
    const ids: string[] = [];
    for await (const v of client.voices.list()) ids.push(v.id);
    expect(ids).toEqual(["v1", "v2"]);
  });

  it("speak picks the first system voice", async () => {
    const voice = (id: string, kind?: string, state = "ready") => ({ id, object: "voice.voice", voice_profile_id: "p", name: id, language: "cs", state, failure_code: null, created_at: "x", ready_at: "x", languages: [], ...(kind ? { kind } : {}) });
    const dl = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(new Uint8Array([9])));
    const { fetch, calls } = queuedFetch([
      json(200, { object: "voice.list", data: [voice("personal1", "personal"), voice("adela", "system")], has_more: false, next_cursor: null }),
      json(200, { id: "g", object: "voice.generation", state: "completed", cost: { unit: "audio_second", status: "reserved", estimated: 1, reserved: 1 } }), // create
      json(200, { id: "g", object: "voice.generation", state: "completed", cost: { unit: "audio_second", status: "final", reserved: 1, consumed: 1, refunded: 0 }, output: { status: "available", format: "mp3", audio_seconds: 1, bytes: 1, sha256: "a".repeat(64), retention_expires_at: "x", url: "https://dl", url_expires_at: "y" } }), // waitFor
    ]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });
    const { generation } = await client.speak({ text: "Ahoj" });
    expect(generation.state).toBe("completed");
    // The create call (2nd request) must have targeted the SYSTEM voice, not the personal one.
    const createBody = await calls[1]!.json();
    expect(createBody.voiceVersionId).toBe("adela");
    dl.mockRestore();
  });
});
