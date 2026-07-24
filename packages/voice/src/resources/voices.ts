import type { MendelioVoice } from "../client.js";
import { ConnectionError, GenerationFailedError } from "../errors.js";
import type {
  CatalogVoice,
  CreateVoiceParams,
  CreateVoiceResponse,
  SubmitVoiceResponse,
  Voice,
  VoiceCatalogPage,
} from "../types.js";

export class VoicesResource {
  constructor(
    private readonly client: MendelioVoice,
    private readonly fetchImpl: typeof fetch,
  ) {}

  /** One page of voices selectable for speech by the current credential. */
  page(params: {
    locale?: string;
    language?: "cs" | "en" | "de";
    search?: string;
    cursor?: string;
    limit?: number;
  } = {}): Promise<VoiceCatalogPage> {
    return this.client.request<VoiceCatalogPage>("GET", "/voices", {
      query: {
        locale: params.locale,
        language: params.language,
        search: params.search,
        cursor: params.cursor,
        limit: params.limit,
      },
    });
  }

  /** Async iterator over every voice selectable for speech by this credential. */
  async *list(params: {
    locale?: string;
    language?: "cs" | "en" | "de";
    search?: string;
    limit?: number;
  } = {}): AsyncGenerator<CatalogVoice, void, unknown> {
    let cursor: string | undefined;
    do {
      const page = await this.page({ ...params, cursor });
      yield* page.data;
      cursor = page.hasMore ? page.nextCursor ?? undefined : undefined;
    } while (cursor);
  }

  /** Found a new clone and get its upload capability. Upload, then submit. */
  create(params: CreateVoiceParams): Promise<CreateVoiceResponse> {
    return this.client.request<CreateVoiceResponse>("POST", "/owned-voices", { body: params });
  }

  get(id: string): Promise<CatalogVoice> {
    return this.client.request<CatalogVoice>("GET", `/voices/${encodeURIComponent(id)}`);
  }

  /** Read one cloned voice owned by this credential. */
  getOwned(id: string): Promise<Voice> {
    return this.client.request<Voice>("GET", `/owned-voices/${encodeURIComponent(id)}`);
  }

  /** Submit an uploaded recording for processing. Idempotent. */
  submit(id: string): Promise<SubmitVoiceResponse> {
    return this.client.request<SubmitVoiceResponse>("POST", `/owned-voices/${encodeURIComponent(id)}/submit`, {
      idempotencyKey: `submit:${id}`,
    });
  }

  /**
   * Create → PUT the recording to the signed upload URL → submit, in one call. Returns the voice
   * without waiting for it to become ready — poll `waitForReady` for that.
   */
  async createFromFile(params: {
    name: string;
    referenceTextId: string;
    voiceProfileId?: string | null;
    rightsAttestation: CreateVoiceParams["rightsAttestation"];
    file: Uint8Array | Blob;
    contentType?: string;
  }): Promise<Voice> {
    const created = await this.create({
      name: params.name,
      referenceTextId: params.referenceTextId,
      voiceProfileId: params.voiceProfileId,
      rightsAttestation: params.rightsAttestation,
    });
    const put = await this.fetchImpl(created.upload.url, {
      method: "PUT",
      headers: { "content-type": params.contentType ?? "audio/wav" },
      body: params.file as BodyInit,
    });
    if (!put.ok) throw new ConnectionError(`Upload failed (HTTP ${put.status}).`);
    await this.submit(created.voice.id);
    return created.voice;
  }

  /** Poll until the voice is ready; throws GenerationFailedError-style on failure. */
  async waitForReady(id: string, options: { timeoutMs?: number; pollIntervalMs?: number } = {}): Promise<Voice> {
    const timeoutMs = options.timeoutMs ?? 600_000;
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const voice = await this.getOwned(id);
      if (voice.state === "ready") return voice;
      if (voice.state === "failed") {
        throw new VoiceFailedError(voice);
      }
      if (Date.now() >= deadline) {
        throw new ConnectionError(`Timed out after ${timeoutMs} ms waiting for voice ${id}.`);
      }
      await sleep(Math.min(options.pollIntervalMs ?? 5_000, deadline - Date.now()));
    }
  }
}

/** A voice that finished in `failed`. Carries the failure_code the API reported. */
export class VoiceFailedError extends Error {
  constructor(readonly voice: Voice) {
    super(`Voice ${voice.id} failed (${voice.failure_code ?? "unknown"}).`);
    this.name = "VoiceFailedError";
  }
}
// Re-export the generation counterpart so callers can catch either from one import site.
export { GenerationFailedError };

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, Math.max(ms, 0)));
}
