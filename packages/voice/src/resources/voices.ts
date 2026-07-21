import type { MendelioVoice } from "../client.js";
import { ConnectionError, GenerationFailedError } from "../errors.js";
import { paginate } from "../pagination.js";
import type {
  CreateVoiceParams,
  CreateVoiceResponse,
  ListResponse,
  SubmitVoiceResponse,
  Voice,
} from "../types.js";

export class VoicesResource {
  constructor(private readonly client: MendelioVoice) {}

  /** One page of voices (system voices lead the first page). */
  page(params: { cursor?: string; limit?: number } = {}): Promise<ListResponse<Voice>> {
    return this.client.request<ListResponse<Voice>>("GET", "/voices", {
      query: { cursor: params.cursor, limit: params.limit },
    });
  }

  /** Async iterator over every voice available to this key. */
  list(): AsyncGenerator<Voice, void, unknown> {
    return paginate<Voice>((cursor) => this.page({ cursor }));
  }

  /** Found a new clone and get its upload capability. Upload, then submit. */
  create(params: CreateVoiceParams): Promise<CreateVoiceResponse> {
    return this.client.request<CreateVoiceResponse>("POST", "/voices", { body: params });
  }

  get(id: string): Promise<Voice> {
    return this.client.request<Voice>("GET", `/voices/${encodeURIComponent(id)}`);
  }

  /** Submit an uploaded recording for processing. Idempotent. */
  submit(id: string): Promise<SubmitVoiceResponse> {
    return this.client.request<SubmitVoiceResponse>("POST", `/voices/${encodeURIComponent(id)}/submit`, {
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
    file: Uint8Array | Blob;
    contentType?: string;
  }): Promise<Voice> {
    const created = await this.create({
      name: params.name,
      referenceTextId: params.referenceTextId,
      voiceProfileId: params.voiceProfileId,
    });
    const put = await fetch(created.upload.url, {
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
      const voice = await this.get(id);
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
