import { describe, expect, it, vi } from "vitest";
import { tryAnonymousSpeech } from "./anonymousDemoClient.js";

function json(body: unknown): Response {
  return Response.json(body, { status: 200 });
}

describe("anonymous stdio demo client", () => {
  it("opens the browser-assisted verification URL and returns the same headless fallback", async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(json({ result: { serverInfo: { name: "mendelio-voice" } } }))
      .mockResolvedValueOnce(json({ result: {
        structuredContent: {
          status: "verification_required",
          user_code: "ABCD-EFGH",
          verification_uri_complete: "https://voice.mendelio.net/demo/verify?code=ABCD-EFGH",
          demo_verification_secret: "secret-secret-secret-secret-secret-12",
          expires_at: "2026-08-01T12:05:00Z",
        },
      } }));
    const openUrl = vi.fn();

    const result = await tryAnonymousSpeech(
      { text: "Ahoj" },
      { fetchImpl, openUrl },
    );

    expect(result).toMatchObject({ status: "verification_required", userCode: "ABCD-EFGH" });
    expect(openUrl).toHaveBeenCalledWith("https://voice.mendelio.net/demo/verify?code=ABCD-EFGH");
    expect(fetchImpl.mock.calls.every((call) => !(call[1]?.headers as Record<string, string>)?.authorization)).toBe(true);
  });

  it("decodes inline MP3 without following a Storage URL", async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(json({ result: { serverInfo: { name: "mendelio-voice" } } }))
      .mockResolvedValueOnce(json({ result: {
        content: [{ type: "audio", mimeType: "audio/mpeg", data: "AQID" }],
        structuredContent: { status: "completed", audio_seconds: 1, public_voice_id: 55 },
      } }));

    const result = await tryAnonymousSpeech(
      { text: "Ahoj", demoVerificationSecret: "secret-secret-secret-secret-secret-12" },
      { fetchImpl, openUrl: vi.fn() },
    );

    expect(result).toEqual({
      status: "completed",
      audio: new Uint8Array([1, 2, 3]),
      audioSeconds: 1,
      publicVoiceId: 55,
    });
  });
});
