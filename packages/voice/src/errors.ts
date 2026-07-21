import type { ErrorEnvelope, ErrorType, Generation } from "./types.js";

/**
 * The error hierarchy. Every non-2xx API response becomes a `VoiceApiError` subclass chosen by the
 * envelope's `error.type`, carrying the machine-readable `code`, the `param` that failed, and the
 * `requestId` (quote it in a support request). Transport failures are `ConnectionError`; a generation
 * that reaches a failed/cancelled terminal state while you wait is a `GenerationFailedError`.
 */
export class VoiceApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly type: ErrorType;
  readonly param: string | null;
  readonly requestId: string;

  constructor(
    status: number,
    body: { type: ErrorType; code: string; message: string; param: string | null; request_id: string },
  ) {
    super(body.message);
    this.name = new.target.name;
    this.status = status;
    this.code = body.code;
    this.type = body.type;
    this.param = body.param;
    this.requestId = body.request_id;
  }

  /** Map an error envelope onto the right subclass. Falls back to ApiError for an unknown type. */
  static fromEnvelope(status: number, json: unknown): VoiceApiError {
    const envelope = json as Partial<ErrorEnvelope>;
    const e = envelope?.error;
    const body = {
      type: (e?.type ?? "api_error") as ErrorType,
      code: e?.code ?? "unknown_error",
      message: e?.message ?? `Request failed with status ${status}.`,
      param: e?.param ?? null,
      request_id: e?.request_id ?? "",
    };
    const Ctor = TYPE_TO_ERROR[body.type] ?? ApiError;
    return new Ctor(status, body);
  }
}

export class AuthenticationError extends VoiceApiError {}
export class PermissionError extends VoiceApiError {}
export class InvalidRequestError extends VoiceApiError {}
export class IdempotencyError extends VoiceApiError {}
export class CapacityError extends VoiceApiError {}
export class ApiError extends VoiceApiError {}

const TYPE_TO_ERROR: Record<ErrorType, new (status: number, body: any) => VoiceApiError> = {
  authentication_error: AuthenticationError,
  permission_error: PermissionError,
  invalid_request_error: InvalidRequestError,
  idempotency_error: IdempotencyError,
  capacity_error: CapacityError,
  api_error: ApiError,
};

/** A network-level failure (DNS, connection reset, timeout) — never a server verdict. */
export class ConnectionError extends Error {
  constructor(message: string, readonly cause?: unknown) {
    super(message);
    this.name = "ConnectionError";
  }
}

/** A generation you were waiting on ended in `failed` or `cancelled`. */
export class GenerationFailedError extends Error {
  constructor(readonly generation: Generation) {
    super(`Generation ${generation.id} ended in state "${generation.state}".`);
    this.name = "GenerationFailedError";
  }
}

/** A webhook whose signature, timestamp, or headers did not verify. */
export class WebhookVerificationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WebhookVerificationError";
  }
}
