import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { MendelioVoice } from "./client.js";
import {
  AuthenticationError,
  CapacityError,
  GenerationFailedError,
  IdempotencyError,
  InvalidRequestError,
  PermissionError,
  RateLimitError,
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
    [429, "rate_limit_error", "rate_limited", RateLimitError],
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
    const previousKey = process.env.MENDELIO_VOICE_API_KEY;
    const previousConfigHome = process.env.XDG_CONFIG_HOME;
    delete process.env.MENDELIO_VOICE_API_KEY;
    process.env.XDG_CONFIG_HOME = mkdtempSync(join(tmpdir(), "mendelio-voice-auth-test-"));
    try {
      const client = new MendelioVoice({ fetch, baseUrl: "https://api.example/v1/audio" });
      await expect(client.balance.get()).rejects.toBeInstanceOf(AuthenticationError);
    } finally {
      if (previousKey === undefined) delete process.env.MENDELIO_VOICE_API_KEY;
      else process.env.MENDELIO_VOICE_API_KEY = previousKey;
      if (previousConfigHome === undefined) delete process.env.XDG_CONFIG_HOME;
      else process.env.XDG_CONFIG_HOME = previousConfigHome;
    }
  });

  it("removes the caller abort listener after a completed request", async () => {
    const { fetch } = queuedFetch([
      json(200, {
        object: "voice.balance",
        unit: "audio_second",
        total: 10,
        reserved: 1,
        available: 9,
        updated_at: "2026-07-24T00:00:00Z",
      }),
    ]);
    const controller = new AbortController();
    const add = vi.spyOn(controller.signal, "addEventListener");
    const remove = vi.spyOn(controller.signal, "removeEventListener");
    const client = new MendelioVoice({ apiKey: KEY, fetch });

    await client.request("GET", "/balance", { signal: controller.signal });

    expect(add).toHaveBeenCalledOnce();
    expect(remove).toHaveBeenCalledOnce();
    expect(remove.mock.calls[0]?.[1]).toBe(add.mock.calls[0]?.[1]);
  });
});

describe("current public API routing", () => {
  it("resolves moving model aliases from the server catalogue", async () => {
    const models = [
      { id: "omnivoice-0.2.0", aliases: ["omnivoice"], default: true },
      { id: "soniox-tts-rt-v2", aliases: ["soniox"], default: false },
    ];
    const { fetch } = queuedFetch([
      json(200, { object: "voice.list", data: models, has_more: false, next_cursor: null }),
      json(200, { object: "voice.list", data: models, has_more: false, next_cursor: null }),
    ]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });

    await expect(client.models.resolve()).resolves.toMatchObject({ id: "omnivoice-0.2.0" });
    await expect(client.models.resolve("soniox")).resolves.toMatchObject({ id: "soniox-tts-rt-v2" });
  });

  it("passes a model alias through the high-level speak helper", async () => {
    const queued = {
      id: "job-1", object: "audio.speech_job", state: "queued",
      work_class: "mendelio_voice_public_batch", model: "soniox-tts-rt-v2",
      model_version: null,
      cost: { unit: "audio_second", status: "reserved", estimated: 1, reserved: 1 },
    };
    const completed = {
      ...queued, state: "completed", voice_version_id: "voice-1",
      cost: { unit: "audio_second", status: "final", reserved: 1, consumed: 1, refunded: 0 },
      output: { status: "available", format: "mp3", audio_seconds: 1, bytes: 1,
        sha256: "a".repeat(64), retention_expires_at: "x", url: "https://download.example/audio",
        url_expires_at: "y" }, created_at: "x", completed_at: "y",
    };
    const { fetch, calls } = queuedFetch([
      json(200, { object: "voice.list", data: [
        { id: "omnivoice-0.2.0", aliases: ["omnivoice"], default: true },
        { id: "soniox-tts-rt-v2", aliases: ["soniox"], default: false },
      ], has_more: false, next_cursor: null }),
      json(202, queued), json(200, completed), new Response(new Uint8Array([1])),
    ]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });

    await client.speak({ text: "Ahoj", voiceVersionId: "voice-1", model: "soniox" });

    expect(await calls[1]!.json()).toMatchObject({ model: "soniox-tts-rt-v2" });
  });

  it("uses the production /v1/audio base for balance", async () => {
    const { fetch, calls } = queuedFetch([
      json(200, {
        object: "voice.balance",
        unit: "audio_second",
        total: 10,
        reserved: 1,
        available: 9,
        updated_at: "2026-07-24T00:00:00Z",
      }),
    ]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });

    await client.balance.get();

    expect(calls.map((call) => call.url)).toEqual([
      "https://api.mendelio.net/v1/audio/balance",
    ]);
  });

  it("creates and reads asynchronous speech jobs through /speech/jobs", async () => {
    const queued = {
      id: "job-1",
      object: "audio.speech_job",
      state: "queued",
      work_class: "mendelio_voice_public_batch",
      model: "omnivoice-0.2.0",
      model_version: null,
      cost: { unit: "audio_second", status: "reserved", estimated: 1, reserved: 1 },
    };
    const completed = {
      ...queued,
      state: "completed",
      voice_version_id: "voice-1",
      cost: { unit: "audio_second", status: "final", reserved: 1, consumed: 1, refunded: 0 },
      output: null,
      created_at: "2026-07-24T00:00:00Z",
      completed_at: "2026-07-24T00:00:01Z",
    };
    const { fetch, calls } = queuedFetch([json(202, queued), json(200, completed)]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });

    await client.generations.create({ text: "Ahoj", voiceVersionId: "voice-1" });
    await client.generations.get("job-1");

    expect(calls.map((call) => [call.method, call.url])).toEqual([
      ["POST", "https://api.mendelio.net/v1/audio/speech/jobs"],
      ["GET", "https://api.mendelio.net/v1/audio/speech/jobs/job-1"],
    ]);
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
      json(200, { id: "gen_1", object: "audio.speech_job", state: "queued", cost: { unit: "audio_second", status: "reserved", estimated: 1, reserved: 1 } }),
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
    const gen = (state: string) => json(200, { id: "g", object: "audio.speech_job", state, cost: { unit: "audio_second", status: "reserved", estimated: 1, reserved: 1 } });
    const { fetch } = queuedFetch([gen("queued"), gen("generating"), gen("completed")]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });
    const result = await client.generations.waitFor("g", { pollIntervalMs: 1 });
    expect(result.state).toBe("completed");
  });

  it("throws GenerationFailedError on failed", async () => {
    const { fetch } = queuedFetch([json(200, { id: "g", object: "audio.speech_job", state: "failed", cost: { unit: "audio_second", status: "reserved", estimated: 1, reserved: 1 } })]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });
    await expect(client.generations.waitFor("g", { pollIntervalMs: 1 })).rejects.toBeInstanceOf(GenerationFailedError);
  });
});

describe("generations.download", () => {
  it("uses the client's injected fetch for the signed audio URL", async () => {
    const globalFetch = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("global fetch must not run"));
    const { fetch, calls } = queuedFetch([new Response(new Uint8Array([7, 8, 9]))]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });
    try {
      const audio = await client.generations.download({
        id: "g",
        object: "audio.speech_job",
        state: "completed",
        work_class: "mendelio_voice_public_batch",
        voice_version_id: "voice-1",
        model: "omnivoice-0.2.0",
        model_version: null,
        cost: { unit: "audio_second", status: "final", reserved: 1, consumed: 1, refunded: 0 },
        output: {
          status: "available",
          format: "mp3",
          audio_seconds: 1,
          bytes: 3,
          sha256: "a".repeat(64),
          retention_expires_at: "x",
          url: "https://download.example/audio",
          url_expires_at: "y",
        },
        created_at: "x",
        completed_at: "y",
      });

      expect(Array.from(audio)).toEqual([7, 8, 9]);
      expect(calls.map((call) => call.url)).toEqual(["https://download.example/audio"]);
      expect(globalFetch).not.toHaveBeenCalled();
    } finally {
      globalFetch.mockRestore();
    }
  });

  it("re-fetches for a fresh URL when the cached output is expired", async () => {
    const { fetch } = queuedFetch([
      json(200, {
        id: "g", object: "audio.speech_job", state: "completed",
        cost: { unit: "audio_second", status: "final", reserved: 1, consumed: 1, refunded: 0 },
        output: { status: "available", format: "mp3", audio_seconds: 1, bytes: 3, sha256: "a".repeat(64), retention_expires_at: "x", url: "https://dl/fresh", url_expires_at: "y" },
      }),
      new Response(new Uint8Array([1, 2, 3])),
    ]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });
    const audio = await client.generations.download({
      id: "g",
      object: "audio.speech_job",
      state: "completed",
      work_class: "mendelio_voice_public_batch",
      voice_version_id: "voice-1",
      model: "omnivoice-0.2.0",
      model_version: null,
      cost: { unit: "audio_second", status: "final", reserved: 1, consumed: 1, refunded: 0 },
      output: { status: "expired", format: "mp3", retention_expires_at: "x" },
      created_at: "x",
      completed_at: "y",
    });
    expect(Array.from(audio)).toEqual([1, 2, 3]);
  });
});

describe("voices pagination + speak", () => {
  it("iterates across pages", async () => {
    const voice = (id: string) => ({
      voiceVersionId: id,
      publicId: null,
      personaName: null,
      displayName: id,
      description: null,
      languageCode: "cs",
      relation: "offered",
      availability: "available",
      capabilities: ["speech"],
      accessClass: "public",
      styleTags: [],
      useCaseTags: [],
      categoryTags: [],
      avatarUrl: null,
      avatarLightUrl: null,
      preview: null,
    });
    const { fetch } = queuedFetch([
      json(200, { data: [voice("v1")], hasMore: true, nextCursor: "c1", revision: 1, etag: "one" }),
      json(200, { data: [voice("v2")], hasMore: false, nextCursor: null, revision: 1, etag: "two" }),
    ]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });
    const ids: string[] = [];
    for await (const v of client.voices.list()) ids.push(v.voiceVersionId);
    expect(ids).toEqual(["v1", "v2"]);
  });

  it("speak picks the first available speech-capable catalog voice", async () => {
    const voice = (
      id: string,
      availability: "available" | "locked",
      capabilities: ("speech" | "preview")[],
    ) => ({
      voiceVersionId: id,
      publicId: null,
      personaName: null,
      displayName: id,
      description: null,
      languageCode: "cs",
      relation: "offered",
      availability,
      capabilities,
      accessClass: "public",
      styleTags: [],
      useCaseTags: [],
      categoryTags: [],
      avatarUrl: null,
      avatarLightUrl: null,
      preview: null,
    });
    const { fetch, calls } = queuedFetch([
      json(200, {
        data: [
          voice("locked", "locked", ["speech"]),
          voice("preview-only", "available", ["preview"]),
          voice("adela", "available", ["speech"]),
        ],
        hasMore: false,
        nextCursor: null,
        revision: 1,
        etag: "catalog",
      }),
      json(200, {
        id: "g",
        object: "audio.speech_job",
        state: "queued",
        work_class: "mendelio_voice_public_batch",
        model: "omnivoice-0.2.0",
        model_version: null,
        cost: { unit: "audio_second", status: "reserved", estimated: 1, reserved: 1 },
      }),
      json(200, {
        id: "g",
        object: "audio.speech_job",
        state: "completed",
        work_class: "mendelio_voice_public_batch",
        voice_version_id: "adela",
        model: "omnivoice-0.2.0",
        model_version: null,
        cost: { unit: "audio_second", status: "final", reserved: 1, consumed: 1, refunded: 0 },
        output: { status: "available", format: "mp3", audio_seconds: 1, bytes: 1, sha256: "a".repeat(64), retention_expires_at: "x", url: "https://dl", url_expires_at: "y" },
        created_at: "x",
        completed_at: "y",
      }),
      new Response(new Uint8Array([9])),
    ]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });
    const { generation, audio } = await client.speak({ text: "Ahoj" });
    expect(generation.state).toBe("completed");
    expect(Array.from(audio)).toEqual([9]);
    const createBody = await calls[1]!.json();
    expect(createBody.voiceVersionId).toBe("adela");
  });

  it("uses the client's injected fetch for the signed voice upload", async () => {
    const globalFetch = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("global fetch must not run"));
    const createdVoice = {
      id: "voice-1",
      object: "voice.voice",
      voice_profile_id: "profile-1",
      name: "Test voice",
      language: "cs",
      state: "awaiting_upload",
      failure_code: null,
      created_at: "x",
      ready_at: null,
      languages: [{ code: "cs", state: "awaiting_upload" }],
      kind: "personal",
    };
    const { fetch, calls } = queuedFetch([
      json(201, {
        voice: createdVoice,
        upload: {
          object: "voice.upload",
          url: "https://upload.example/reference",
          expires_at: "y",
        },
      }),
      new Response(null, { status: 200 }),
      json(200, {
        object: "voice.submit",
        voice_version_id: "voice-1",
        acceptance: "processing",
      }),
    ]);
    const client = new MendelioVoice({ apiKey: KEY, fetch });
    try {
      const result = await client.voices.createFromFile({
        name: "Test voice",
        referenceTextId: "prompt-cs",
        file: new Uint8Array([1, 2, 3]),
        rightsAttestation: {
          accepted: true,
          version: "2026-07-22-v1",
          speakerRelationship: "self",
        },
      });

      expect(result.id).toBe("voice-1");
      expect(calls.map((call) => [call.method, call.url])).toEqual([
        ["POST", "https://api.mendelio.net/v1/audio/owned-voices"],
        ["PUT", "https://upload.example/reference"],
        ["POST", "https://api.mendelio.net/v1/audio/owned-voices/voice-1/submit"],
      ]);
      expect(await calls[0]!.json()).toMatchObject({
        name: "Test voice",
        referenceTextId: "prompt-cs",
        rightsAttestation: {
          accepted: true,
          version: "2026-07-22-v1",
          speakerRelationship: "self",
        },
      });
      expect(calls[1]!.headers.get("content-type")).toBe("audio/wav");
      expect(Array.from(new Uint8Array(await calls[1]!.arrayBuffer()))).toEqual([1, 2, 3]);
      expect(globalFetch).not.toHaveBeenCalled();
    } finally {
      globalFetch.mockRestore();
    }
  });
});
