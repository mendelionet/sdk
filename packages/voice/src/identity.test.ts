import { describe, expect, it } from "vitest";

import { MENDELIO_VOICE_IDENTITY } from "./identity.js";

describe("Mendelio Voice identity", () => {
  it("keeps every public surface under the canonical technical family", () => {
    expect(MENDELIO_VOICE_IDENTITY.technical.machineName).toBe("mendelio-voice");
    expect(MENDELIO_VOICE_IDENTITY.surfaces.hezkyCesky.machineName).toBe(
      "mendelio-voice-hezky-cesky",
    );
    expect(MENDELIO_VOICE_IDENTITY.mcp.packageName).toBe("mendelio-voice-mcp");
  });

  it("publishes one canonical origin for each external adapter", () => {
    expect(
      new Set([
        MENDELIO_VOICE_IDENTITY.surfaces.studio.origin,
        MENDELIO_VOICE_IDENTITY.surfaces.hezkyCesky.origin,
        MENDELIO_VOICE_IDENTITY.urls.apiOrigin,
      ]).size,
    ).toBe(3);
    expect(MENDELIO_VOICE_IDENTITY.urls.mcp).toBe(
      `${MENDELIO_VOICE_IDENTITY.urls.apiOrigin}/mcp`,
    );
  });

  it("records the verified catalogue floor as structured identity data", () => {
    expect(MENDELIO_VOICE_IDENTITY.catalog.minimumUniqueVoices).toBe(190);
    expect(MENDELIO_VOICE_IDENTITY.catalog.highlights).toEqual(
      expect.arrayContaining([
        "creatures and fantasy characters",
        "dragons",
        "robots and synthetic characters",
      ]),
    );
  });

  it("keeps npm package metadata within the registry limit", () => {
    expect(MENDELIO_VOICE_IDENTITY.mcp.packageDescription.length).toBeLessThanOrEqual(255);
  });
});
