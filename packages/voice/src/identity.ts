import identity from "./identity.json";

/**
 * Canonical public and technical identity for the Mendelio Voice family.
 *
 * Product surfaces, SDKs, MCP adapters, API descriptions, and release metadata should derive
 * names, origins, discovery phrases, and capability claims from this value instead of copying
 * them. Operation-specific UI copy remains with the owning localized surface.
 */
export const MENDELIO_VOICE_IDENTITY = identity;
export type MendelioVoiceIdentity = typeof MENDELIO_VOICE_IDENTITY;

export const MENDELIO_VOICE_RELEASE_STAGE_LABELS = {
  public_preview: "Public Preview",
} as const satisfies Record<typeof MENDELIO_VOICE_IDENTITY.mcp.releaseStage, string>;
