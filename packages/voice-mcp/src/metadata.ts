import { MENDELIO_VOICE_MCP_VERSION } from "./version.js";
import { MENDELIO_VOICE_IDENTITY } from "mendelio-voice";

const identity = MENDELIO_VOICE_IDENTITY;

export const MENDELIO_VOICE_MCP_SERVER_INFO = {
  name: identity.technical.machineName,
  title: identity.mcp.displayName,
  version: MENDELIO_VOICE_MCP_VERSION,
  description: identity.mcp.description,
  websiteUrl: identity.urls.developers,
} as const;

export const MENDELIO_VOICE_MCP_INSTRUCTIONS = identity.mcp.instructions;
