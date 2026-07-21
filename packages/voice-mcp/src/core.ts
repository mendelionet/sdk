import { z } from "zod";
import type { MendelioVoice, Voice } from "mendelio-voice";
import { VoiceApiError } from "mendelio-voice";

/**
 * Transport-agnostic tool definitions, shared by the local stdio server (index.ts) and the remote
 * Streamable-HTTP server (api.mendelio.net/mcp). `buildTools` takes a context so the two transports
 * can differ where they must — the remote server has no local filesystem, so it drops output paths,
 * microphone capture and login and hands back links instead.
 */
export interface ToolContent {
  content: { type: "text"; text: string }[];
}
export interface ToolDef {
  name: string;
  description: string;
  inputSchema: z.ZodRawShape;
  handler: (args: Record<string, unknown>) => Promise<ToolContent>;
}

export interface ToolContext {
  /** The authenticated SDK client, or null when no key is available. */
  client: () => MendelioVoice | null;
  mode: "local" | "remote";
  /** local only: begin device login and return the code + URL immediately. */
  login?: () => Promise<{ userCode: string; verificationUriComplete: string }>;
  /** local only: record from the microphone to a WAV path for the given seconds. */
  record?: (seconds: number) => Promise<{ ok: true; path: string } | { ok: false; hint: string }>;
  /** local only: where generated audio is written. */
  writeAudio?: (bytes: Uint8Array, suggestedName: string) => string;
}

const WIZARD_URL = "https://voice.mendelio.net/voices";
const CREDIT_URL = "https://voice.mendelio.net/credit";

function text(s: string): ToolContent {
  return { content: [{ type: "text", text: s }] };
}

/** Turn an API error into an actionable line — never leak a key, always suggest the next step. */
function explain(err: unknown): string {
  if (err instanceof VoiceApiError) {
    if (err.code === "insufficient_credit") return `Not enough credit. Top up at ${CREDIT_URL}.`;
    if (err.code === "capacity_saturated") return "Voice capacity is busy right now — try again in a moment.";
    if (err.code === "authentication_required") return "Not signed in — call voice_login.";
    return `${err.code}: ${err.message}`;
  }
  return err instanceof Error ? err.message : String(err);
}

function voiceLine(v: Voice): string {
  return `- ${v.id} — ${v.name} [${v.language}] (${v.kind ?? "personal"}, ${v.state})`;
}

export function buildTools(ctx: ToolContext): ToolDef[] {
  const local = ctx.mode === "local";

  const requireClient = (): MendelioVoice | { notLoggedIn: true } => {
    const c = ctx.client();
    return c ?? { notLoggedIn: true };
  };

  const tools: ToolDef[] = [];

  tools.push({
    name: "voice_generate_speech",
    description:
      "Generate speech from text with Mendelio Voice. Without voice_version_id it uses a system voice.",
    inputSchema: {
      text: z.string().describe("The text to speak."),
      voice_version_id: z.string().uuid().optional().describe("A specific voice id from voice_list_voices."),
      format: z.enum(["mp3", "wav"]).optional(),
      ...(local ? { output_path: z.string().optional().describe("Where to write the audio file.") } : {}),
    },
    handler: async (args) => {
      const c = requireClient();
      if ("notLoggedIn" in c) return text("Not signed in — call voice_login.");
      try {
        if (ctx.mode === "remote") {
          // No filesystem: create + wait, then hand back the short-lived signed URL.
          const created = await c.generations.create({
            text: String(args.text),
            voiceVersionId: args.voice_version_id as string | undefined,
            format: args.format as "mp3" | "wav" | undefined,
          });
          const gen = await c.generations.waitFor(created.id);
          const url = gen.output?.status === "available" ? gen.output.url : null;
          return text(url
            ? `Generated ${gen.output && "audio_seconds" in gen.output ? gen.output.audio_seconds : "?"}s of audio.\nDownload (expires soon): ${url}`
            : `Generation ${gen.id} completed but has no downloadable output.`);
        }
        const { generation, audio } = await c.speak({
          text: String(args.text),
          voiceVersionId: args.voice_version_id as string | undefined,
          format: args.format as "mp3" | "wav" | undefined,
        });
        const fmt = args.format ?? "mp3";
        const path = ctx.writeAudio!(audio, String(args.output_path ?? `voice-${generation.id.slice(0, 8)}.${fmt}`));
        const secs = generation.output && "audio_seconds" in generation.output ? generation.output.audio_seconds : "?";
        return text(`Saved ${path} (${secs}s of audio, generation ${generation.id}).`);
      } catch (err) {
        return text(explain(err));
      }
    },
  });

  tools.push({
    name: "voice_list_voices",
    description: "List available voices (system voices you can use immediately, and your own clones).",
    inputSchema: {},
    handler: async () => {
      const c = requireClient();
      if ("notLoggedIn" in c) return text("Not signed in — call voice_login.");
      try {
        const voices: Voice[] = [];
        for await (const v of c.voices.list()) voices.push(v);
        return text(voices.length ? voices.map(voiceLine).join("\n") : "No voices yet.");
      } catch (err) {
        return text(explain(err));
      }
    },
  });

  tools.push({
    name: "voice_get_generation",
    description: "Get the status, cost and output metadata of a generation.",
    inputSchema: { generation_id: z.string().uuid() },
    handler: async (args) => {
      const c = requireClient();
      if ("notLoggedIn" in c) return text("Not signed in — call voice_login.");
      try {
        const g = await c.generations.get(String(args.generation_id));
        return text(`Generation ${g.id}: ${g.state}. Cost: ${JSON.stringify(g.cost)}. Output: ${JSON.stringify(g.output ?? null)}`);
      } catch (err) {
        return text(explain(err));
      }
    },
  });

  tools.push({
    name: "voice_get_balance",
    description: "Read your Mendelio Voice credit balance (audio seconds).",
    inputSchema: {},
    handler: async () => {
      const c = requireClient();
      if ("notLoggedIn" in c) return text("Not signed in — call voice_login.");
      try {
        const b = await c.balance.get();
        return text(`Balance: ${b.available} available, ${b.reserved} reserved, ${b.total} total (audio seconds).`);
      } catch (err) {
        return text(explain(err));
      }
    },
  });

  tools.push({
    name: "voice_list_reference_prompts",
    description: "List the reference texts you read aloud when cloning a voice.",
    inputSchema: { language: z.enum(["cs", "en", "de"]).optional() },
    handler: async (args) => {
      const c = requireClient();
      if ("notLoggedIn" in c) return text("Not signed in — call voice_login.");
      try {
        const prompts = await c.referencePrompts.list({ language: args.language as "cs" | "en" | "de" | undefined });
        return text(
          "Read one of these aloud when recording, then pass its id to clone:\n" +
            prompts.map((p) => `- ${p.id} [${p.language}]: ${p.text}`).join("\n"),
        );
      } catch (err) {
        return text(explain(err));
      }
    },
  });

  tools.push({
    name: "voice_clone_voice",
    description: local
      ? "Clone a voice from a WAV recording file and the reference text you read aloud."
      : "Begin cloning a voice: returns an upload URL to PUT your WAV recording to, then submit.",
    inputSchema: {
      name: z.string(),
      reference_text_id: z.string(),
      ...(local ? { audio_path: z.string().describe("Path to your WAV recording.") } : {}),
    },
    handler: async (args) => {
      const c = requireClient();
      if ("notLoggedIn" in c) return text("Not signed in — call voice_login.");
      try {
        if (ctx.mode === "remote") {
          const created = await c.voices.create({
            name: String(args.name),
            referenceTextId: String(args.reference_text_id),
          });
          return text(
            `Voice ${created.voice.id} created. PUT your WAV recording to this URL (expires soon), then call voice_get_generation is not needed — the server processes it:\n${created.upload.url}`,
          );
        }
        const { readFileSync } = await import("node:fs");
        const file = readFileSync(String(args.audio_path));
        const voice = await c.voices.createFromFile({
          name: String(args.name),
          referenceTextId: String(args.reference_text_id),
          file,
        });
        const ready = await c.voices.waitForReady(voice.id);
        return text(`Voice ready: ${ready.id} — ${ready.name} [${ready.language}].`);
      } catch (err) {
        return text(explain(err));
      }
    },
  });

  if (local && ctx.record) {
    tools.push({
      name: "voice_record_and_clone",
      description:
        "Record from the microphone and clone a voice. Call once to get a reference text, then again with confirmed:true when the person is ready to read it.",
      inputSchema: {
        name: z.string(),
        reference_text_id: z.string().optional(),
        duration_seconds: z.number().optional(),
        confirmed: z.boolean().optional(),
      },
      handler: async (args) => {
        const c = requireClient();
        if ("notLoggedIn" in c) return text("Not signed in — call voice_login.");
        try {
          if (!args.reference_text_id) {
            const prompts = await c.referencePrompts.list();
            return text(
              "Pick a reference_text_id and call again:\n" +
                prompts.map((p) => `- ${p.id} [${p.language}]: ${p.text}`).join("\n"),
            );
          }
          const prompts = await c.referencePrompts.list();
          const prompt = prompts.find((p) => p.id === args.reference_text_id);
          if (!prompt) return text("Unknown reference_text_id — call voice_list_reference_prompts.");
          if (!args.confirmed) {
            return text(
              `Tell the person to have this text in front of them and read it clearly:\n\n"${prompt.text}"\n\nWhen ready, call again with confirmed:true.`,
            );
          }
          const rec = await ctx.record!(Number(args.duration_seconds ?? 12));
          if (!rec.ok) return text(rec.hint);
          const { readFileSync } = await import("node:fs");
          const voice = await c.voices.createFromFile({
            name: String(args.name),
            referenceTextId: String(args.reference_text_id),
            file: readFileSync(rec.path),
          });
          const ready = await c.voices.waitForReady(voice.id);
          return text(`Recorded and cloned: ${ready.id} — ${ready.name} [${ready.language}].`);
        } catch (err) {
          return text(explain(err));
        }
      },
    });
  } else if (!local) {
    // Remote clients have no microphone — point them at the web wizard.
    tools.push({
      name: "voice_record_and_clone",
      description: "Record-and-clone needs a microphone, which the remote server does not have.",
      inputSchema: {},
      handler: async () => text(`Use the web quick-clone wizard: ${WIZARD_URL}`),
    });
  }

  if (local && ctx.login) {
    tools.push({
      name: "voice_login",
      description: "Sign in to Mendelio Voice (opens a browser; one click to approve).",
      inputSchema: {},
      handler: async () => {
        try {
          const { userCode, verificationUriComplete } = await ctx.login!();
          return text(
            `Open this link and approve (or send it to the user):\n${verificationUriComplete}\nCode: ${userCode}\n\nOnce approved, the next tool call will use your key automatically.`,
          );
        } catch (err) {
          return text(explain(err));
        }
      },
    });
  }

  return tools;
}
