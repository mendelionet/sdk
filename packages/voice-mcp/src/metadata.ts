import { MENDELIO_VOICE_MCP_VERSION } from "./version.js";
import {
  MENDELIO_VOICE_IDENTITY,
  MENDELIO_VOICE_RELEASE_STAGE_LABELS,
} from "mendelio-voice/identity";

const identity = MENDELIO_VOICE_IDENTITY;
const releaseStageLabel = MENDELIO_VOICE_RELEASE_STAGE_LABELS[
  identity.mcp.releaseStage as keyof typeof MENDELIO_VOICE_RELEASE_STAGE_LABELS
];

export const MENDELIO_VOICE_MCP_RELEASE_STAGE = identity.mcp.releaseStage;

export const MENDELIO_VOICE_MCP_SERVER_INFO = {
  name: identity.technical.machineName,
  title: `${identity.mcp.displayName} — ${releaseStageLabel}`,
  version: MENDELIO_VOICE_MCP_VERSION,
  description: `${releaseStageLabel} — ${identity.mcp.description}`,
  websiteUrl: identity.urls.developers,
} as const;

export const MENDELIO_VOICE_MCP_INSTRUCTIONS = identity.mcp.instructions;
