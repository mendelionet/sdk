/**
 * Wire types for the Mendelio Voice API, 1:1 with the HTTP contract.
 *
 * Responses are snake_case (as the server sends them); request bodies are camelCase (as the server
 * accepts them). The SDK does NOT rename fields — what you read is what the API returned, so the
 * OpenAPI spec and these types can never drift into different vocabularies.
 */

export type Format = "mp3" | "wav";
export type LanguageCode = "cs" | "en" | "de";

export type GenerationState =
  | "queued"
  | "preparing_capacity"
  | "generating"
  | "encoding"
  | "completed"
  | "failed"
  | "cancelling"
  | "cancelled";

export type PublicVoiceState = "awaiting_upload" | "processing" | "ready" | "failed";
export type VoiceKind = "system" | "personal";

export interface ReservedCost {
  unit: "audio_second";
  status: "reserved";
  estimated: number;
  reserved: number;
}
export interface FinalCost {
  unit: "audio_second";
  status: "final";
  reserved: number;
  consumed: number;
  refunded: number;
}
export type CostProjection = ReservedCost | FinalCost;

export interface AvailableGenerationOutput {
  status: "available";
  format: Format;
  audio_seconds: number;
  bytes: number;
  sha256: string;
  retention_expires_at: string;
  /** Short-lived, minted per GET. Download promptly; never store it as a durable link. */
  url: string;
  url_expires_at: string;
}
export interface ExpiredGenerationOutput {
  status: "expired";
  format: Format;
  retention_expires_at: string;
}
export type ReadGenerationOutput = AvailableGenerationOutput | ExpiredGenerationOutput | null;

export interface Generation {
  id: string;
  object: "voice.generation";
  state: GenerationState;
  work_class?: string;
  voice_version_id?: string;
  model?: string;
  model_version?: string | null;
  cost: CostProjection;
  output?: ReadGenerationOutput;
  created_at?: string;
  completed_at?: string | null;
}

export interface VoiceLanguageState {
  code: LanguageCode;
  state: PublicVoiceState;
}
export interface Voice {
  id: string;
  object: "voice.voice";
  voice_profile_id: string;
  name: string;
  language: LanguageCode;
  state: PublicVoiceState;
  failure_code: string | null;
  created_at: string;
  ready_at: string | null;
  languages: VoiceLanguageState[];
  /** system = a platform voice usable by anyone; personal = your own clone. */
  kind?: VoiceKind;
}

export interface VoiceUpload {
  object: "voice.upload";
  url: string;
  expires_at: string;
}
export interface CreateVoiceResponse {
  voice: Voice;
  upload: VoiceUpload;
}
export interface SubmitVoiceResponse {
  object: "voice.submit";
  voice_version_id: string;
  acceptance: string;
}

export interface Model {
  id: string;
  object: "voice.model";
  default: boolean;
  languages: LanguageCode[];
  billing: { unit: "audio_second"; rate: number };
}
export interface ReferencePrompt {
  id: string;
  object: "voice.reference_prompt";
  language: LanguageCode;
  text: string;
}
export interface Balance {
  object: "voice.balance";
  unit: "audio_second";
  total: number;
  reserved: number;
  available: number;
  updated_at: string;
}

/** Cursor-paginated list envelope. */
export interface ListResponse<T> {
  object: "voice.list";
  data: T[];
  has_more: boolean;
  next_cursor: string | null;
}

// --- Request shapes (camelCase) ---

export interface GenerateParams {
  text: string;
  voiceVersionId?: string;
  model?: string;
  format?: Format;
}
export interface CreateVoiceParams {
  name: string;
  referenceTextId: string;
  voiceProfileId?: string | null;
}

// --- Error envelope ---

export type ErrorType =
  | "authentication_error"
  | "permission_error"
  | "invalid_request_error"
  | "idempotency_error"
  | "capacity_error"
  | "api_error";

export interface ErrorEnvelope {
  error: {
    type: ErrorType;
    code: string;
    message: string;
    param: string | null;
    request_id: string;
  };
}

// --- Webhooks ---

export type WebhookEventType =
  | "generation.completed"
  | "generation.failed"
  | "generation.cancelled"
  | "voice.ready"
  | "voice.failed";

export interface WebhookEvent {
  id: string;
  type: WebhookEventType;
  /** Unix seconds. */
  created: number;
  data: Record<string, unknown>;
}
