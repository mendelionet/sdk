import { z } from "zod";
import type {
  Balance,
  CatalogVoice,
  CreateGeneration,
  GenerateParams,
  Generation,
  LanguageCode,
  ReferencePrompt,
  Voice,
} from "mendelio-voice";
import { VoiceApiError } from "mendelio-voice";

/**
 * Transport-agnostic tool definitions shared by the local stdio server and the remote
 * Streamable HTTP server. A client is supplied per call so remote requests never share credentials.
 */
export interface ToolContent {
  [key: string]: unknown;
  content: { type: "text"; text: string }[];
  structuredContent: Record<string, unknown>;
  isError?: boolean;
}

export interface ToolDef {
  name: string;
  description: string;
  inputSchema: z.ZodRawShape;
  handler: (args: Record<string, unknown>) => Promise<ToolContent>;
}

/**
 * The complete transport-neutral capability required by the shared remote tool set.
 * Implementations may call the public SDK or the platform domain directly; the core never knows.
 */
export interface VoiceMcpOperations {
  listVoices(): Promise<CatalogVoice[]>;
  createGeneration(params: GenerateParams): Promise<CreateGeneration>;
  waitForGeneration(id: string): Promise<Generation>;
  getGeneration(id: string): Promise<Generation>;
  getBalance(): Promise<Balance>;
  listReferencePrompts(params?: { language?: LanguageCode }): Promise<ReferencePrompt[]>;
}

/** Local-only operations that are intentionally impossible to provide to remote mode. */
export interface LocalVoiceMcpOperations extends VoiceMcpOperations {
  synthesizeAndDownload(params: GenerateParams): Promise<{
    generation: Generation;
    audio: Uint8Array;
  }>;
  cloneVoiceFromFile(args: {
    name: string;
    referenceTextId: string;
    audioPath: string;
    speakerRelationship: "self" | "authorized";
  }): Promise<Voice>;
}

interface SharedToolContext<Operations extends VoiceMcpOperations> {
  /** Request-scoped operations, or null when no trusted principal is available. */
  operations: () => Operations | null;
}

export interface RemoteToolContext extends SharedToolContext<VoiceMcpOperations> {
  mode: "remote";
}

export interface LocalToolContext extends SharedToolContext<LocalVoiceMcpOperations> {
  mode: "local";
  /** Where generated audio is written. Required because local generation always writes a file. */
  writeAudio: (bytes: Uint8Array, suggestedName: string) => string;
  /** Local only: begin device login and return the code + URL immediately. */
  login?: () => Promise<{ userCode: string; verificationUriComplete: string }>;
  /** Local only: record from the microphone to a WAV path for the given seconds. */
  record?: (seconds: number) => Promise<{ ok: true; path: string } | { ok: false; hint: string }>;
}

export type ToolContext = LocalToolContext | RemoteToolContext;

const WIZARD_URL = "https://voice.mendelio.net/voices";
const CREDIT_URL = "https://voice.mendelio.net/credit";

function result(
  summary: string,
  structuredContent: Record<string, unknown>,
  isError = false,
): ToolContent {
  return {
    content: [{ type: "text", text: summary }],
    structuredContent,
    ...(isError ? { isError: true } : {}),
  };
}

function notAuthenticated(mode: ToolContext["mode"]): ToolContent {
  const action = mode === "local" ? "voice_login" : "reauthorize_connector";
  const summary =
    mode === "local"
      ? "Not signed in. Call voice_login first."
      : "The connector is not authorized. Reconnect it and complete OAuth authorization.";
  return result(summary, { status: "authentication_required", action });
}

/** Preserve actionable API meaning without reflecting credentials or unknown internal messages. */
function apiFailure(error: unknown): ToolContent {
  if (error instanceof VoiceApiError || isOperationError(error)) {
    const actions: Record<string, { summary: string; action: string }> = {
      authentication_required: {
        summary: "Authentication is no longer valid. Sign in or reconnect the connector.",
        action: "reauthorize",
      },
      permission_denied: {
        summary: "The current credential does not grant the required permission.",
        action: "grant_required_scope",
      },
      insufficient_credit: {
        summary: `Not enough credit. Top up at ${CREDIT_URL}.`,
        action: "top_up_credit",
      },
      capacity_saturated: {
        summary: "Voice capacity is busy. Try the request again later.",
        action: "retry_later",
      },
      capacity_unavailable: {
        summary: "Voice capacity is temporarily unavailable. Try the request again later.",
        action: "retry_later",
      },
      rate_limited: {
        summary: "Too many requests. Try the request again later.",
        action: "retry_later",
      },
    };
    const known = actions[error.code];
    return result(
      known?.summary ?? `The Voice API rejected the request (${error.code}).`,
      {
        status: "api_error",
        code: error.code,
        action: known?.action ?? "review_request",
        ...(error.requestId ? { request_id: error.requestId } : {}),
      },
      true,
    );
  }
  return result(
    "The Voice request could not be completed.",
    { status: "request_failed", action: "retry_or_check_connection" },
    true,
  );
}

function isOperationError(error: unknown): error is { code: string; requestId?: string } {
  return !!error && typeof error === "object" && typeof (error as { code?: unknown }).code === "string";
}

function publicVoice(voice: Voice): Record<string, unknown> {
  return {
    id: voice.id,
    name: voice.name,
    language: voice.language,
    languages: voice.languages,
    kind: voice.kind,
    state: voice.state,
    failure_code: voice.failure_code,
  };
}

function publicCatalogVoice(voice: CatalogVoice): Record<string, unknown> {
  return {
    id: voice.voiceVersionId,
    public_id: voice.publicId,
    persona_name: voice.personaName,
    name: voice.displayName,
    description: voice.description,
    ...(voice.sampleText !== undefined ? { sample_text: voice.sampleText } : {}),
    language: voice.languageCode,
    relation: voice.relation,
    availability: voice.availability,
    capabilities: voice.capabilities,
    access_class: voice.accessClass,
    style_tags: voice.styleTags,
    use_case_tags: voice.useCaseTags,
    category_tags: voice.categoryTags,
    avatar_url: voice.avatarUrl,
    avatar_light_url: voice.avatarLightUrl,
    preview: voice.preview,
    ...(voice.safeReason ? { safe_reason: voice.safeReason } : {}),
  };
}

function publicGeneration(generation: Generation): Record<string, unknown> {
  return {
    id: generation.id,
    state: generation.state,
    voice_version_id: generation.voice_version_id,
    model: generation.model,
    cost: generation.cost,
    output: generation.output,
  };
}

function publicReferencePrompt(prompt: ReferencePrompt): Record<string, unknown> {
  return {
    id: prompt.id,
    language: prompt.language,
    text: prompt.text,
  };
}

async function readyVoices(operations: VoiceMcpOperations): Promise<CatalogVoice[]> {
  return (await operations.listVoices()).filter(
    (voice) => voice.availability === "available" && voice.capabilities.includes("speech"),
  );
}

async function resolveGenerationVoice(
  operations: VoiceMcpOperations,
  requestedVoiceId: unknown,
): Promise<{ voiceVersionId: string } | ToolContent> {
  if (typeof requestedVoiceId === "string") return { voiceVersionId: requestedVoiceId };
  const voices = await readyVoices(operations);
  if (voices.length === 1) return { voiceVersionId: voices[0]!.voiceVersionId };
  if (voices.length === 0) {
    return result(
      "No ready voice is available. Open the voice wizard to create one.",
      { status: "no_ready_voice", action: "open_voice_wizard", url: WIZARD_URL },
    );
  }
  return result(
    "Choose a voice_version_id from the available ready voices and call the tool again.",
    {
      status: "voice_selection_required",
      voices: voices.map(publicCatalogVoice),
    },
  );
}

async function cloneVoiceFromFile(
  operations: LocalVoiceMcpOperations,
  args: {
    name: string;
    referenceTextId: string;
    audioPath: string;
    speakerRelationship: "self" | "authorized";
  },
): Promise<ToolContent> {
  const ready = await operations.cloneVoiceFromFile(args);
  return result(`Voice ${ready.name} is ready.`, {
    status: "ready",
    voice: publicVoice(ready),
  });
}

export function buildTools(ctx: ToolContext): ToolDef[] {
  const localContext = ctx.mode === "local" ? ctx : null;
  const local = localContext !== null;
  const tools: ToolDef[] = [];

  tools.push({
    name: "voice_generate_speech",
    description:
      "Generate speech from text. If several voices are ready, first returns the choices and asks for voice_version_id.",
    inputSchema: {
      text: z.string().min(1).describe("The text to speak."),
      voice_version_id: z.string().uuid().optional().describe("A specific voice id from voice_list_voices."),
      format: z.enum(["mp3", "wav"]).optional(),
      ...(local ? { output_path: z.string().optional().describe("Where to write the audio file.") } : {}),
    },
    handler: async (args) => {
      const operations = ctx.operations();
      if (!operations) return notAuthenticated(ctx.mode);
      try {
        const resolved = await resolveGenerationVoice(operations, args.voice_version_id);
        if ("content" in resolved) return resolved;
        const format = args.format as "mp3" | "wav" | undefined;

        if (!localContext) {
          const created = await operations.createGeneration({
            text: String(args.text),
            voiceVersionId: resolved.voiceVersionId,
            format,
          });
          const generation = await operations.waitForGeneration(created.id);
          if (generation.output?.status !== "available") {
            return result(
              `Generation ${generation.id} completed without a downloadable output.`,
              { status: "output_unavailable", generation: publicGeneration(generation) },
              true,
            );
          }
          return result(
            `Generated ${generation.output.audio_seconds}s of audio. The download URL expires at ${generation.output.url_expires_at}.`,
            { status: "completed", generation: publicGeneration(generation) },
          );
        }

        const { generation, audio } = await (operations as LocalVoiceMcpOperations).synthesizeAndDownload({
          text: String(args.text),
          voiceVersionId: resolved.voiceVersionId,
          format,
        });
        const selectedFormat = format ?? "mp3";
        const path = localContext.writeAudio(
          audio,
          String(args.output_path ?? `voice-${generation.id.slice(0, 8)}.${selectedFormat}`),
        );
        const audioSeconds =
          generation.output?.status === "available" ? generation.output.audio_seconds : null;
        return result(
          `Saved generated audio to ${path}.`,
          {
            status: "completed",
            path,
            format: selectedFormat,
            audio_seconds: audioSeconds,
            voice_version_id: resolved.voiceVersionId,
            generation: publicGeneration(generation),
          },
        );
      } catch (error) {
        return apiFailure(error);
      }
    },
  });

  tools.push({
    name: "voice_list_voices",
    description: "List available system voices and personal clones.",
    inputSchema: {},
    handler: async () => {
      const operations = ctx.operations();
      if (!operations) return notAuthenticated(ctx.mode);
      try {
        const voices = await operations.listVoices();
        return result(
          voices.length ? `Found ${voices.length} voice(s).` : "No voices are available.",
          { voices: voices.map(publicCatalogVoice) },
        );
      } catch (error) {
        return apiFailure(error);
      }
    },
  });

  tools.push({
    name: "voice_get_generation",
    description: "Get the state, cost and output metadata of a generation.",
    inputSchema: { generation_id: z.string().uuid() },
    handler: async (args) => {
      const operations = ctx.operations();
      if (!operations) return notAuthenticated(ctx.mode);
      try {
        const generation = await operations.getGeneration(String(args.generation_id));
        return result(
          `Generation ${generation.id} is ${generation.state}.`,
          { generation: publicGeneration(generation) },
        );
      } catch (error) {
        return apiFailure(error);
      }
    },
  });

  tools.push({
    name: "voice_get_balance",
    description: "Read the current Mendelio Voice credit balance in audio seconds.",
    inputSchema: {},
    handler: async () => {
      const operations = ctx.operations();
      if (!operations) return notAuthenticated(ctx.mode);
      try {
        const balance = await operations.getBalance();
        return result(
          `${balance.available} audio seconds are available.`,
          {
            balance: {
              unit: balance.unit,
              total: balance.total,
              reserved: balance.reserved,
              available: balance.available,
              updated_at: balance.updated_at,
            },
          },
        );
      } catch (error) {
        return apiFailure(error);
      }
    },
  });

  tools.push({
    name: "voice_list_reference_prompts",
    description: "List the exact reference texts that can be read aloud when cloning a voice.",
    inputSchema: { language: z.enum(["cs", "en", "de"]).optional() },
    handler: async (args) => {
      const operations = ctx.operations();
      if (!operations) return notAuthenticated(ctx.mode);
      try {
        const prompts = await operations.listReferencePrompts({
          language: args.language as "cs" | "en" | "de" | undefined,
        });
        return result(
          `Found ${prompts.length} reference prompt(s). Read the chosen text exactly when cloning.`,
          { prompts: prompts.map(publicReferencePrompt) },
        );
      } catch (error) {
        return apiFailure(error);
      }
    },
  });

  if (local) {
    tools.push({
      name: "voice_clone_voice",
      description: "Clone a voice from a local WAV recording and wait until it is ready or failed.",
      inputSchema: {
        name: z.string().min(1),
        reference_text_id: z.string().min(1),
        audio_path: z.string().min(1).describe("Path to the WAV recording."),
        rights_confirmed: z.literal(true).describe("Confirm that the speaker granted the required cloning rights."),
        speaker_relationship: z.enum(["self", "authorized"]),
      },
      handler: async (args) => {
        const operations = ctx.operations();
        if (!operations) return notAuthenticated(ctx.mode);
        try {
          return await cloneVoiceFromFile(operations as LocalVoiceMcpOperations, {
            name: String(args.name),
            referenceTextId: String(args.reference_text_id),
            audioPath: String(args.audio_path),
            speakerRelationship: args.speaker_relationship as "self" | "authorized",
          });
        } catch (error) {
          return apiFailure(error);
        }
      },
    });
  } else {
    tools.push({
      name: "voice_clone_voice",
      description:
        "Get the browser flow for recording and cloning a voice. This remote tool does not upload audio.",
      inputSchema: {},
      handler: async () =>
        result(
          "Record and clone the voice in the Mendelio Voice web wizard.",
          { status: "web_flow_required", action: "open_voice_wizard", url: WIZARD_URL },
        ),
    });
  }

  if (localContext?.record) {
    const record = localContext.record;
    tools.push({
      name: "voice_record_and_clone",
      description:
        "Record from the local microphone and clone a voice after the reference text has been confirmed.",
      inputSchema: {
        name: z.string().min(1),
        reference_text_id: z.string().optional(),
        duration_seconds: z.number().min(3).max(60).optional(),
        confirmed: z.boolean().optional(),
        rights_confirmed: z.literal(true).optional().describe("Confirm that the speaker granted the required cloning rights."),
        speaker_relationship: z.enum(["self", "authorized"]).optional(),
      },
      handler: async (args) => {
        const operations = ctx.operations();
        if (!operations) return notAuthenticated(ctx.mode);
        try {
          if (!args.reference_text_id) {
            const prompts = await operations.listReferencePrompts();
            return result(
              "Choose a reference_text_id and call the tool again.",
              {
                status: "reference_prompt_required",
                prompts: prompts.map(publicReferencePrompt),
              },
            );
          }
          const prompts = await operations.listReferencePrompts();
          const prompt = prompts.find((candidate) => candidate.id === args.reference_text_id);
          if (!prompt) {
            return result(
              "The reference_text_id is not available.",
              { status: "invalid_reference_prompt", action: "list_reference_prompts" },
              true,
            );
          }
          if (!args.confirmed) {
            return result(
              "Have the speaker read the supplied reference text, then call again with confirmed:true.",
              {
                status: "confirmation_required",
                prompt: publicReferencePrompt(prompt),
              },
            );
          }
          if (args.rights_confirmed !== true || !args.speaker_relationship) {
            return result(
              "Confirm the speaker's cloning rights before recording.",
              { status: "rights_confirmation_required", action: "confirm_cloning_rights" },
              true,
            );
          }
          const recording = await record(Number(args.duration_seconds ?? 12));
          if (!recording.ok) {
            return result(
              recording.hint,
              { status: "recorder_unavailable", action: "provide_audio_file", url: WIZARD_URL },
              true,
            );
          }
          return await cloneVoiceFromFile(operations as LocalVoiceMcpOperations, {
            name: String(args.name),
            referenceTextId: String(args.reference_text_id),
            audioPath: recording.path,
            speakerRelationship: args.speaker_relationship as "self" | "authorized",
          });
        } catch (error) {
          return apiFailure(error);
        }
      },
    });
  }

  if (localContext?.login) {
    const loginDevice = localContext.login;
    tools.push({
      name: "voice_login",
      description: "Begin Mendelio Voice device login and return the one-click approval URL.",
      inputSchema: {},
      handler: async () => {
        try {
          const login = await loginDevice();
          return result(
            "Open the authorization URL and approve access. A later tool call will use the saved credential.",
            {
              status: "authorization_required",
              user_code: login.userCode,
              verification_uri_complete: login.verificationUriComplete,
            },
          );
        } catch (error) {
          return apiFailure(error);
        }
      },
    });
  }

  return tools;
}
