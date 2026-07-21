export { MendelioVoice } from "./client.js";
export type { MendelioVoiceOptions, RequestOptions } from "./client.js";

export {
  ApiError,
  AuthenticationError,
  CapacityError,
  ConnectionError,
  GenerationFailedError,
  IdempotencyError,
  InvalidRequestError,
  PermissionError,
  VoiceApiError,
  WebhookVerificationError,
} from "./errors.js";
export { VoiceFailedError } from "./resources/voices.js";

export { constructEvent, verifySignature } from "./webhooks.js";
export type { VerifyOptions } from "./webhooks.js";

export { deviceLogin } from "./login.js";
export type { DeviceLoginOptions } from "./login.js";
export { readCredentials, writeCredentials, clearCredentials } from "./credentials.js";
export type { Credentials } from "./credentials.js";

export type {
  Balance,
  CostProjection,
  CreateVoiceParams,
  CreateVoiceResponse,
  ErrorEnvelope,
  ErrorType,
  Format,
  FinalCost,
  GenerateParams,
  Generation,
  GenerationState,
  InputNormalization,
  LanguageCode,
  ListResponse,
  Model,
  PublicVoiceState,
  ReferencePrompt,
  ReadGenerationOutput,
  ReservedCost,
  SubmitVoiceResponse,
  Voice,
  VoiceKind,
  VoiceLanguageState,
  VoiceUpload,
  WebhookEvent,
  WebhookEventType,
} from "./types.js";
