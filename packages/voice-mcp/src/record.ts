import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WIZARD_URL = "https://voice.mendelio.net/voices";

/**
 * Record `seconds` of mono 48 kHz audio from the default microphone to a temp WAV, trying `sox` then
 * `ffmpeg` per platform. If neither is present (or capture fails), returns a fallback hint rather than
 * throwing — the server-side trim (podcast-renderer) cleans up the countdown/silence, so we do not
 * trim here.
 */
export async function recordMicrophone(
  seconds: number,
): Promise<{ ok: true; path: string } | { ok: false; hint: string }> {
  const out = join(tmpdir(), `mendelio-voice-${Date.now()}.wav`);
  const dur = Math.max(3, Math.min(seconds, 60));

  const attempts = candidates(out, dur);
  for (const [cmd, args] of attempts) {
    if (!(await inPath(cmd))) continue;
    const ok = await run(cmd, args);
    if (ok) return { ok: true, path: out };
  }
  return {
    ok: false,
    hint:
      "No microphone recorder found (install `sox` or `ffmpeg`). Record a WAV yourself and call " +
      `voice_clone_voice with its path, or use the web wizard: ${WIZARD_URL}`,
  };
}

function candidates(out: string, dur: number): [string, string[]][] {
  if (process.platform === "darwin") {
    return [
      ["sox", ["-d", "-c", "1", "-r", "48000", out, "trim", "0", String(dur)]],
      ["ffmpeg", ["-y", "-f", "avfoundation", "-i", ":0", "-t", String(dur), "-ac", "1", "-ar", "48000", out]],
    ];
  }
  if (process.platform === "win32") {
    return [["ffmpeg", ["-y", "-f", "dshow", "-i", "audio=default", "-t", String(dur), "-ac", "1", "-ar", "48000", out]]];
  }
  return [
    ["sox", ["-d", "-c", "1", "-r", "48000", out, "trim", "0", String(dur)]],
    ["ffmpeg", ["-y", "-f", "alsa", "-i", "default", "-t", String(dur), "-ac", "1", "-ar", "48000", out]],
  ];
}

function inPath(cmd: string): Promise<boolean> {
  return run(process.platform === "win32" ? "where" : "which", [cmd], true);
}

function run(cmd: string, args: string[], quiet = false): Promise<boolean> {
  return new Promise((resolve) => {
    try {
      const child = spawn(cmd, args, { stdio: quiet ? "ignore" : "inherit" });
      child.on("error", () => resolve(false));
      child.on("close", (code) => resolve(code === 0));
    } catch {
      resolve(false);
    }
  });
}
