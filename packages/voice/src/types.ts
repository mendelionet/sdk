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
export type SpeechWorkClass =
  | "live_first_chunk"
  | "live_followup_chunk"
  | "mendelio_internal_batch"
  | "mendelio_voice_public_batch";

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

export interface CreateGeneration {
  id: string;
  object: "audio.speech_job";
  state: GenerationState;
  work_class: SpeechWorkClass;
  model: "mendelio-voice-1";
  model_version: string | null;
  cost: ReservedCost;
}

export interface Generation {
  id: string;
  object: "audio.speech_job";
  state: GenerationState;
  work_class: SpeechWorkClass;
  voice_version_id: string;
  model: "mendelio-voice-1";
  model_version: string | null;
  cost: CostProjection;
  output: ReadGenerationOutput;
  created_at: string;
  completed_at: string | null;
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
  kind: VoiceKind;
}

export interface CatalogVoice {
  voiceVersionId: string;
  displayName: string;
  languageCode: LanguageCode;
  relation: "own" | "shared" | "offered";
  availability: "available" | "locked" | "temporarily_unavailable";
  safeReason?: "upgrade_required" | "sign_in_required" | "temporarily_unavailable";
  capabilities: ("speech" | "preview" | "live-agent" | "podcast")[];
  accessClass: "public" | "basic" | "premium" | "donor" | "internal";
  styleTags: string[];
  useCaseTags: string[];
  preview: { url: string; expiresAt: string } | null;
}

export interface VoiceCatalogPage {
  data: CatalogVoice[];
  nextCursor: string | null;
  hasMore: boolean;
  revision: number;
  etag: string;
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
  acceptance: "enqueued" | "already_enqueued";
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
  voiceVersionId: string;
  model?: "mendelio-voice-1" | null;
  format?: Format;
  store?: boolean;
}
export interface CreateVoiceParams {
  name: string;
  referenceTextId: string;
  voiceProfileId?: string | null;
  rightsAttestation: {
    accepted: true;
    version: "2026-07-22-v1";
    speakerRelationship: "self" | "authorized";
  };
}

// --- Error envelope ---

export type ErrorType =
  | "authentication_error"
  | "permission_error"
  | "invalid_request_error"
  | "idempotency_error"
  | "rate_limit_error"
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
  | "speech_job.completed"
  | "speech_job.failed"
  | "speech_job.cancelled"
  | "voice.ready"
  | "voice.failed"
  | "transcription.completed"
  | "transcription.failed"
  | "transcription.expired";

export interface WebhookEvent {
  id: string;
  type: WebhookEventType;
  /** Unix seconds. */
  created: number;
  data: Record<string, unknown>;
}
