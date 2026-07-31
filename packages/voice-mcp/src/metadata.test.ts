import { describe, expect, it } from "vitest";
import { MENDELIO_VOICE_IDENTITY } from "mendelio-voice/identity";
import {
  MENDELIO_VOICE_MCP_RELEASE_STAGE,
} from "./metadata.js";

describe("MCP release metadata", () => {
  it("projects the structured identity release stage into connected server metadata", () => {
    expect(MENDELIO_VOICE_MCP_RELEASE_STAGE).toBe(MENDELIO_VOICE_IDENTITY.mcp.releaseStage);
    expect(MENDELIO_VOICE_MCP_RELEASE_STAGE).toBe("public_preview");
  });
});
