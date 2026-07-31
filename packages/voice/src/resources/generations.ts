import type { MendelioVoice } from "../client.js";
import { ConnectionError, GenerationFailedError, InvalidRequestError } from "../errors.js";
import type { CreateGeneration, Generation, GenerateParams } from "../types.js";

export interface WaitForOptions {
  timeoutMs?: number;
  pollIntervalMs?: number;
  onState?: (generation: Generation) => void;
  signal?: AbortSignal;
}

export class GenerationsResource {
  constructor(
    private readonly client: MendelioVoice,
    private readonly fetchImpl: typeof fetch,
  ) {}

  /**
   * Create a generation. Idempotency-Key defaults to a fresh UUID so a network retry replays rather
   * than double-charging; pass your own to make the whole call safely retriable across processes.
   */
  create(params: GenerateParams, options: { idempotencyKey?: string; signal?: AbortSignal } = {}): Promise<CreateGeneration> {
    return this.client.request<CreateGeneration>("POST", "/speech/jobs", {
      body: params,
      idempotencyKey: options.idempotencyKey ?? randomUuid(),
      signal: options.signal,
    });
  }

  /** Fetch a generation's current state and (when completed) its short-lived output. */
  get(id: string): Promise<Generation> {
    return this.client.request<Generation>("GET", `/speech/jobs/${encodeURIComponent(id)}`);
  }

  /**
   * Poll until the generation reaches a terminal state. Returns a completed generation; throws
   * GenerationFailedError on failed/cancelled, ConnectionError on timeout. Polls every 1 s for the
   * first 10 s, then every 5 s.
   */
  async waitFor(id: string, options: WaitForOptions = {}): Promise<Generation> {
    const timeoutMs = options.timeoutMs ?? 300_000;
    const deadline = Date.now() + timeoutMs;
    const started = Date.now();
    for (;;) {
      const generation = await this.get(id);
      options.onState?.(generation);
      if (generation.state === "completed") return generation;
      if (generation.state === "failed" || generation.state === "cancelled") {
        throw new GenerationFailedError(generation);
      }
      if (Date.now() >= deadline) {
        throw new ConnectionError(`Timed out after ${timeoutMs} ms waiting for generation ${id}.`);
      }
      const interval = options.pollIntervalMs ?? (Date.now() - started < 10_000 ? 1_000 : 5_000);
      await sleep(Math.min(interval, deadline - Date.now()), options.signal);
    }
  }

  /**
   * Download a completed generation's audio. Output URLs are minted per GET and expire, so on a
   * 403/expired URL this re-fetches the generation once for a fresh URL before failing.
   */
  async download(generation: Generation): Promise<Uint8Array> {
    let output = generation.output;
    if (!output || output.status !== "available") {
      const fresh = await this.get(generation.id);
      output = fresh.output;
    }
    if (!output || output.status !== "available") {
      throw new InvalidRequestError(400, {
        type: "invalid_request_error",
        code: "generation_not_completed",
        message: `Generation ${generation.id} has no downloadable output (status: ${output?.status ?? "null"}).`,
        param: null,
        request_id: "",
      });
    }

    let res = await this.fetchImpl(output.url);
    if (res.status === 403 || res.status === 404) {
      const fresh = await this.get(generation.id);
      if (fresh.output?.status === "available") res = await this.fetchImpl(fresh.output.url);
    }
    if (!res.ok) {
      throw new ConnectionError(`Failed to download audio (HTTP ${res.status}).`);
    }
    return new Uint8Array(await res.arrayBuffer());
  }
}

function randomUuid(): string {
  return globalThis.crypto.randomUUID();
}
function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const onAbort = () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      reject(signal?.reason);
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, Math.max(ms, 0));
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}
