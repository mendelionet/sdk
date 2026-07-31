import { MENDELIO_VOICE_IDENTITY, openExternalUrl } from "mendelio-voice";
import type { TrySpeechParams, TrySpeechResult } from "./core.js";

interface ToolPayload {
  result?: {
    isError?: boolean;
    content?: Array<{ type?: string; data?: string; mimeType?: string }>;
    structuredContent?: Record<string, unknown>;
  };
  error?: { message?: string };
}

/** Thin stdio-to-remote adapter. It never reads or writes account credentials. */
export async function tryAnonymousSpeech(
  params: TrySpeechParams,
  dependencies: { fetchImpl?: typeof fetch; openUrl?: (url: string) => void } = {},
): Promise<TrySpeechResult> {
  const fetchImpl = dependencies.fetchImpl ?? globalThis.fetch;
  const endpoint = process.env.MENDELIO_VOICE_MCP_URL?.trim()
    || `${MENDELIO_VOICE_IDENTITY.urls.apiOrigin}/mcp`;
  await postMcp(fetchImpl, endpoint, {
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: {
      protocolVersion: "2025-06-18",
      capabilities: {},
      clientInfo: { name: "mendelio-voice-mcp-stdio", version: "0.1.4" },
    },
  });
  const payload = await postMcp(fetchImpl, endpoint, {
    jsonrpc: "2.0",
    id: 2,
    method: "tools/call",
    params: {
      name: "voice_try_speech",
      arguments: {
        text: params.text,
        ...(params.publicVoiceId !== undefined ? { public_voice_id: params.publicVoiceId } : {}),
        ...(params.demoVerificationSecret
          ? { demo_verification_secret: params.demoVerificationSecret }
          : {}),
      },
    },
  });
  const structured = payload.result?.structuredContent ?? {};
  if (structured.status === "verification_required") {
    const result: TrySpeechResult = {
      status: "verification_required",
      userCode: requiredString(structured.user_code),
      verificationUriComplete: requiredString(structured.verification_uri_complete),
      demoVerificationSecret: requiredString(structured.demo_verification_secret),
      expiresAt: requiredString(structured.expires_at),
    };
    (dependencies.openUrl ?? openExternalUrl)(result.verificationUriComplete);
    return result;
  }
  if (payload.result?.isError || payload.error || structured.status !== "completed") {
    throw operationError(typeof structured.code === "string" ? structured.code : "capacity_unavailable");
  }
  const audio = payload.result?.content?.find((block) => block.type === "audio" && block.mimeType === "audio/mpeg");
  if (!audio?.data) throw operationError("capacity_unavailable");
  return {
    status: "completed",
    audio: Uint8Array.from(Buffer.from(audio.data, "base64")),
    audioSeconds: Number(structured.audio_seconds),
    publicVoiceId: Number(structured.public_voice_id),
  };
}

async function postMcp(fetchImpl: typeof fetch, endpoint: string, body: Record<string, unknown>): Promise<ToolPayload> {
  const response = await fetchImpl(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
    },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({})) as ToolPayload;
  if (!response.ok || payload.error) throw operationError(response.status === 429 ? "rate_limited" : "capacity_unavailable");
  return payload;
}

function requiredString(value: unknown): string {
  if (typeof value !== "string" || !value) throw operationError("capacity_unavailable");
  return value;
}

function operationError(code: string): Error & { code: string } {
  return Object.assign(new Error(code), { code });
}
