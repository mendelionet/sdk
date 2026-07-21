import { MendelioVoice, readCredentials } from "mendelio-voice";

/**
 * Resolve an authenticated client, or null when there is no key yet. Re-checked on every tool call so
 * that a login completing in the background is picked up by the next call. The key is never returned
 * or logged — only whether one exists.
 */
export function resolveClient(): MendelioVoice | null {
  const hasKey = Boolean(process.env.MENDELIO_VOICE_API_KEY) || Boolean(readCredentials()?.api_key);
  return hasKey ? new MendelioVoice() : null;
}
