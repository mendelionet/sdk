import { AuthenticationError, ConnectionError, VoiceApiError } from "./errors.js";
import { readCredentials } from "./credentials.js";
import { GenerationsResource } from "./resources/generations.js";
import { VoicesResource } from "./resources/voices.js";
import { ModelsResource } from "./resources/models.js";
import { ReferencePromptsResource } from "./resources/referencePrompts.js";
import { BalanceResource } from "./resources/balance.js";
import type { Format, Generation, InputNormalization } from "./types.js";

const VERSION = "0.1.0";
const DEFAULT_BASE_URL = "https://api.mendelio.net/v1/voice";

export interface MendelioVoiceOptions {
  /** Falls back to $MENDELIO_VOICE_API_KEY, then ~/.config/mendelio/credentials.json. */
  apiKey?: string;
  baseUrl?: string;
  /** Retries for idempotent situations only (GET, or POST with an idempotency key). Default 2. */
  maxRetries?: number;
  /** Per-request timeout. Default 60_000 ms. */
  timeoutMs?: number;
  /** Injectable fetch — for tests or a custom agent. Defaults to the global fetch. */
  fetch?: typeof fetch;
}

export interface RequestOptions {
  query?: Record<string, string | number | undefined>;
  body?: unknown;
  idempotencyKey?: string;
  signal?: AbortSignal;
}

const RETRIABLE_STATUS = new Set([429, 500, 502, 503, 504]);

/** A Mendelio Voice API client. Construct once and reuse; it holds no per-request state. */
export class MendelioVoice {
  readonly baseUrl: string;
  private readonly maxRetries: number;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;
  private apiKey: string | undefined;
  private resolvedKey = false;

  readonly generations: GenerationsResource;
  readonly voices: VoicesResource;
  readonly models: ModelsResource;
  readonly referencePrompts: ReferencePromptsResource;
  readonly balance: BalanceResource;

  constructor(options: MendelioVoiceOptions = {}) {
    this.apiKey = options.apiKey;
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/$/, "");
    this.maxRetries = options.maxRetries ?? 2;
    this.timeoutMs = options.timeoutMs ?? 60_000;
    this.fetchImpl = options.fetch ?? globalThis.fetch;
    this.generations = new GenerationsResource(this);
    this.voices = new VoicesResource(this);
    this.models = new ModelsResource(this);
    this.referencePrompts = new ReferencePromptsResource(this);
    this.balance = new BalanceResource(this);
  }

  /** Resolve the key lazily at first use: opts → env → credentials file. */
  private resolveKey(): string {
    if (!this.resolvedKey) {
      this.apiKey =
        this.apiKey ?? process.env.MENDELIO_VOICE_API_KEY ?? readCredentials()?.api_key ?? undefined;
      this.resolvedKey = true;
    }
    if (!this.apiKey) {
      throw new AuthenticationError(401, {
        type: "authentication_error",
        code: "authentication_required",
        message: "No API key. Run `npx mendelio-voice login` or set MENDELIO_VOICE_API_KEY.",
        param: null,
        request_id: "",
      });
    }
    return this.apiKey;
  }

  /** Low-level request with retry + timeout. Resources call this; you usually will not. */
  async request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
    const key = this.resolveKey();
    const url = new URL(this.baseUrl + path);
    for (const [k, v] of Object.entries(options.query ?? {})) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }

    const headers: Record<string, string> = {
      authorization: `Bearer ${key}`,
      "user-agent": `mendelio-voice/${VERSION} node/${process.version}`,
      accept: "application/json",
    };
    if (options.body !== undefined) headers["content-type"] = "application/json";
    if (options.idempotencyKey) headers["idempotency-key"] = options.idempotencyKey;

    // Retry idempotent situations only: a GET, or a POST carrying an idempotency key (so a retry
    // replays rather than double-charges). Never a bare POST.
    const retriable = method === "GET" || Boolean(options.idempotencyKey);
    const maxAttempts = retriable ? this.maxRetries + 1 : 1;

    let lastError: unknown;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const timeout = new AbortController();
      const timer = setTimeout(() => timeout.abort(), this.timeoutMs);
      const signal = options.signal
        ? anySignal([options.signal, timeout.signal])
        : timeout.signal;
      let res: Response;
      try {
        res = await this.fetchImpl(url, {
          method,
          headers,
          body: options.body === undefined ? undefined : JSON.stringify(options.body),
          signal,
        });
      } catch (cause) {
        clearTimeout(timer);
        lastError = new ConnectionError(
          cause instanceof Error ? cause.message : "Network request failed.",
          cause,
        );
        if (attempt < maxAttempts - 1) {
          await sleep(this.backoff(attempt, null));
          continue;
        }
        throw lastError;
      }
      clearTimeout(timer);

      if (res.ok) return (await res.json()) as T;

      const json = await res.json().catch(() => ({}));
      const error = VoiceApiError.fromEnvelope(res.status, json);
      if (RETRIABLE_STATUS.has(res.status) && attempt < maxAttempts - 1) {
        lastError = error;
        await sleep(this.backoff(attempt, res.headers.get("retry-after")));
        continue;
      }
      throw error;
    }
    throw lastError;
  }

  /** Retry-After (seconds) wins; otherwise exponential backoff with jitter, capped at 8 s. */
  private backoff(attempt: number, retryAfter: string | null): number {
    if (retryAfter) {
      const secs = Number(retryAfter);
      if (Number.isFinite(secs) && secs >= 0) return secs * 1000;
    }
    return Math.min(2 ** attempt * 500 + Math.random() * 250, 8000);
  }

  /**
   * Generate speech and return the finished generation plus its audio bytes. Without a
   * voiceVersionId it picks the first system voice, else the first ready voice.
   */
  async speak(params: {
    text: string;
    voiceVersionId?: string;
    format?: Format;
    inputNormalization?: InputNormalization;
  }): Promise<{ generation: Generation; audio: Uint8Array }> {
    let voiceVersionId = params.voiceVersionId;
    if (!voiceVersionId) {
      const voices: import("./types.js").Voice[] = [];
      for await (const voice of this.voices.list()) voices.push(voice);
      const pick = voices.find((v) => v.kind === "system") ?? voices.find((v) => v.state === "ready");
      if (!pick) {
        throw new (await import("./errors.js")).InvalidRequestError(400, {
          type: "invalid_request_error",
          code: "invalid_request",
          message: "No voiceVersionId given and no usable voice found. Create one or pass an id.",
          param: "voiceVersionId",
          request_id: "",
        });
      }
      voiceVersionId = pick.id;
    }
    const created = await this.generations.create({
      text: params.text,
      voiceVersionId,
      format: params.format,
      inputNormalization: params.inputNormalization,
    });
    const generation = await this.generations.waitFor(created.id);
    const audio = await this.generations.download(generation);
    return { generation, audio };
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/** Combine abort signals — the user's and the timeout's — without requiring AbortSignal.any. */
function anySignal(signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController();
  for (const s of signals) {
    if (s.aborted) {
      controller.abort(s.reason);
      break;
    }
    s.addEventListener("abort", () => controller.abort(s.reason), { once: true });
  }
  return controller.signal;
}
