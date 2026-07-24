import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import type {
  Balance,
  CatalogVoice,
  Generation,
  MendelioVoice,
  ReferencePrompt,
  Voice,
} from "mendelio-voice";
import { VoiceApiError } from "mendelio-voice";
import { buildTools, type ToolDef } from "./core.js";

const VOICE_ID_A = "00000000-0000-4000-8000-000000000001";
const VOICE_ID_B = "00000000-0000-4000-8000-000000000002";
const GENERATION_ID = "00000000-0000-4000-8000-000000000003";

function voice(id = VOICE_ID_A, overrides: Partial<Voice> = {}): Voice {
  return {
    id,
    object: "voice.voice",
    voice_profile_id: "profile",
    name: "Adéla",
    language: "cs",
    state: "ready",
    failure_code: null,
    created_at: "2026-07-23T00:00:00Z",
    ready_at: "2026-07-23T00:00:00Z",
    languages: [{ code: "cs", state: "ready" }],
    kind: "system",
    ...overrides,
  };
}

function catalogVoice(id = VOICE_ID_A, overrides: Partial<CatalogVoice> = {}): CatalogVoice {
  return {
    voiceVersionId: id,
    displayName: "Adéla",
    languageCode: "cs",
    relation: "offered",
    availability: "available",
    capabilities: ["speech"],
    accessClass: "public",
    styleTags: [],
    useCaseTags: [],
    preview: null,
    ...overrides,
  };
}

function generation(overrides: Partial<Generation> = {}): Generation {
  return {
    id: GENERATION_ID,
    object: "audio.speech_job",
    state: "completed",
    work_class: "mendelio_voice_public_batch",
    voice_version_id: VOICE_ID_A,
    model: "mendelio-voice-1",
    model_version: null,
    cost: {
      unit: "audio_second",
      status: "final",
      reserved: 2,
      consumed: 2,
      refunded: 0,
    },
    output: {
      status: "available",
      format: "mp3",
      audio_seconds: 2,
      bytes: 3,
      sha256: "a".repeat(64),
      retention_expires_at: "2026-07-30T00:00:00Z",
      url: "https://download.example/audio",
      url_expires_at: "2026-07-23T00:15:00Z",
    },
    created_at: "2026-07-23T00:00:00Z",
    completed_at: "2026-07-23T00:00:02Z",
    ...overrides,
  };
}

function asyncValues<T>(values: T[]): AsyncGenerator<T, void, unknown> {
  return (async function* () {
    yield* values;
  })();
}

function fakeClient(options: {
  voices?: CatalogVoice[];
  generation?: Generation;
  balance?: Balance;
  prompts?: ReferencePrompt[];
} = {}) {
  const listedVoices = options.voices ?? [catalogVoice()];
  const finished = options.generation ?? generation();
  const balance = options.balance ?? {
    object: "voice.balance" as const,
    unit: "audio_second" as const,
    total: 20,
    reserved: 2,
    available: 18,
    updated_at: "2026-07-23T00:00:00Z",
  };
  const prompts = options.prompts ?? [
    {
      id: "prompt-cs",
      object: "voice.reference_prompt" as const,
      language: "cs" as const,
      text: "Referenční text",
    },
  ];
  const calls = {
    createGeneration: vi.fn(async () => generation({ state: "queued", output: null })),
    waitForGeneration: vi.fn(async () => finished),
    getGeneration: vi.fn(async () => finished),
    getBalance: vi.fn(async () => balance),
    listPrompts: vi.fn(async () => prompts),
    createVoice: vi.fn(async () => voice()),
    waitForVoice: vi.fn(async () => voice()),
    speak: vi.fn(async () => ({ generation: finished, audio: new Uint8Array([1, 2, 3]) })),
  };
  const client = {
    voices: {
      list: () => asyncValues(listedVoices),
      createFromFile: calls.createVoice,
      waitForReady: calls.waitForVoice,
    },
    generations: {
      create: calls.createGeneration,
      waitFor: calls.waitForGeneration,
      get: calls.getGeneration,
    },
    balance: { get: calls.getBalance },
    referencePrompts: { list: calls.listPrompts },
    speak: calls.speak,
  } as unknown as MendelioVoice;
  return { client, calls };
}

function byName(tools: ToolDef[], name: string): ToolDef {
  const tool = tools.find((candidate) => candidate.name === name);
  if (!tool) throw new Error(`Missing tool ${name}`);
  return tool;
}

describe("buildTools modes", () => {
  it("keeps filesystem, microphone and login capabilities local", () => {
    const { client } = fakeClient();
    const local = buildTools({
      mode: "local",
      client: () => client,
      login: async () => ({ userCode: "ABCD-EFGH", verificationUriComplete: "https://login.example" }),
      record: async () => ({ ok: true, path: "/tmp/voice.wav" }),
      writeAudio: () => "/tmp/audio.mp3",
    });
    const remote = buildTools({ mode: "remote", client: () => client });

    expect(local.map((tool) => tool.name)).toEqual([
      "voice_generate_speech",
      "voice_list_voices",
      "voice_get_generation",
      "voice_get_balance",
      "voice_list_reference_prompts",
      "voice_clone_voice",
      "voice_record_and_clone",
      "voice_login",
    ]);
    expect(remote.map((tool) => tool.name)).toEqual([
      "voice_generate_speech",
      "voice_list_voices",
      "voice_get_generation",
      "voice_get_balance",
      "voice_list_reference_prompts",
      "voice_clone_voice",
    ]);
    expect(Object.keys(byName(local, "voice_generate_speech").inputSchema)).toContain("output_path");
    expect(Object.keys(byName(remote, "voice_generate_speech").inputSchema)).not.toContain("output_path");
    expect(Object.keys(byName(local, "voice_clone_voice").inputSchema)).toContain("audio_path");
    expect(Object.keys(byName(local, "voice_clone_voice").inputSchema)).toEqual(
      expect.arrayContaining(["rights_confirmed", "speaker_relationship"]),
    );
    expect(Object.keys(byName(remote, "voice_clone_voice").inputSchema)).toEqual([]);
  });

  it("does not create a voice from the remote web-flow tool", async () => {
    const { client, calls } = fakeClient();
    const tool = byName(buildTools({ mode: "remote", client: () => client }), "voice_clone_voice");
    const response = await tool.handler({});

    expect(response.structuredContent).toMatchObject({
      status: "web_flow_required",
      action: "open_voice_wizard",
    });
    expect(calls.createVoice).not.toHaveBeenCalled();
  });

  it("returns mode-specific authentication recovery without invoking an SDK client", async () => {
    const local = buildTools({ mode: "local", client: () => null });
    const remote = buildTools({ mode: "remote", client: () => null });

    const localResult = await byName(local, "voice_get_balance").handler({});
    const remoteResult = await byName(remote, "voice_get_balance").handler({});

    expect(localResult.structuredContent).toEqual({
      status: "authentication_required",
      action: "voice_login",
    });
    expect(remoteResult.structuredContent).toEqual({
      status: "authentication_required",
      action: "reauthorize_connector",
    });
  });

  it("returns only the device authorization contract from local login", async () => {
    const { client } = fakeClient();
    const login = vi.fn(async () => ({
      userCode: "ABCD-EFGH",
      verificationUriComplete: "https://voice.example/activate?code=ABCD-EFGH",
    }));
    const tool = byName(buildTools({ mode: "local", client: () => client, login }), "voice_login");
    const response = await tool.handler({});

    expect(login).toHaveBeenCalledOnce();
    expect(response.structuredContent).toEqual({
      status: "authorization_required",
      user_code: "ABCD-EFGH",
      verification_uri_complete: "https://voice.example/activate?code=ABCD-EFGH",
    });
    expect(Object.keys(response.structuredContent)).not.toContain("api_key");
  });
});

describe("tool SDK contracts", () => {
  it("reports the no-ready-voice state without starting a generation", async () => {
    const { client, calls } = fakeClient({
      voices: [catalogVoice(VOICE_ID_A, { availability: "temporarily_unavailable" })],
    });
    const tool = byName(buildTools({ mode: "remote", client: () => client }), "voice_generate_speech");
    const response = await tool.handler({ text: "Ahoj" });

    expect(response.structuredContent).toMatchObject({
      status: "no_ready_voice",
      action: "open_voice_wizard",
    });
    expect(calls.createGeneration).not.toHaveBeenCalled();
  });

  it("requires an explicit choice when several voices are ready", async () => {
    const { client, calls } = fakeClient({
      voices: [catalogVoice(VOICE_ID_A), catalogVoice(VOICE_ID_B, { displayName: "Štěpán" })],
    });
    const tool = byName(buildTools({ mode: "remote", client: () => client }), "voice_generate_speech");
    const response = await tool.handler({ text: "Ahoj" });

    expect(response.structuredContent).toMatchObject({
      status: "voice_selection_required",
      voices: [{ id: VOICE_ID_A }, { id: VOICE_ID_B }],
    });
    expect(calls.createGeneration).not.toHaveBeenCalled();
  });

  it("passes normalized remote generation arguments and returns output metadata", async () => {
    const { client, calls } = fakeClient();
    const tool = byName(buildTools({ mode: "remote", client: () => client }), "voice_generate_speech");
    const response = await tool.handler({ text: "Ahoj", format: "wav" });

    expect(calls.createGeneration).toHaveBeenCalledWith({
      text: "Ahoj",
      voiceVersionId: VOICE_ID_A,
      format: "wav",
    });
    expect(calls.waitForGeneration).toHaveBeenCalledWith(GENERATION_ID);
    expect(response.structuredContent).toMatchObject({
      status: "completed",
      generation: {
        id: GENERATION_ID,
        voice_version_id: VOICE_ID_A,
        output: {
          status: "available",
          url: "https://download.example/audio",
        },
      },
    });
  });

  it("passes local generation arguments and returns the written path", async () => {
    const { client, calls } = fakeClient();
    const writeAudio = vi.fn(() => "/safe/result.mp3");
    const tool = byName(
      buildTools({ mode: "local", client: () => client, writeAudio }),
      "voice_generate_speech",
    );
    const response = await tool.handler({
      text: "Ahoj",
      voice_version_id: VOICE_ID_A,
      output_path: "result.mp3",
    });

    expect(calls.speak).toHaveBeenCalledWith({
      text: "Ahoj",
      voiceVersionId: VOICE_ID_A,
      format: undefined,
    });
    expect(writeAudio).toHaveBeenCalledWith(expect.any(Uint8Array), "result.mp3");
    expect(response.structuredContent).toMatchObject({
      status: "completed",
      path: "/safe/result.mp3",
      voice_version_id: VOICE_ID_A,
    });
  });

  it("maps list, get, balance and reference prompt results to structured contracts", async () => {
    const { client, calls } = fakeClient();
    const tools = buildTools({ mode: "remote", client: () => client });

    const voices = await byName(tools, "voice_list_voices").handler({});
    const generationResult = await byName(tools, "voice_get_generation").handler({
      generation_id: GENERATION_ID,
    });
    const balance = await byName(tools, "voice_get_balance").handler({});
    const prompts = await byName(tools, "voice_list_reference_prompts").handler({ language: "cs" });

    expect(voices.structuredContent).toMatchObject({
      voices: [{ id: VOICE_ID_A, relation: "offered", availability: "available" }],
    });
    expect(generationResult.structuredContent).toMatchObject({ generation: { id: GENERATION_ID } });
    expect(balance.structuredContent).toMatchObject({ balance: { available: 18, reserved: 2 } });
    expect(prompts.structuredContent).toMatchObject({ prompts: [{ id: "prompt-cs", language: "cs" }] });
    expect(calls.getGeneration).toHaveBeenCalledWith(GENERATION_ID);
    expect(calls.listPrompts).toHaveBeenCalledWith({ language: "cs" });
  });

  it("runs local clone create-upload-submit through the SDK and waits for ready", async () => {
    const { client, calls } = fakeClient();
    const dir = mkdtempSync(join(tmpdir(), "mendelio-mcp-test-"));
    const audioPath = join(dir, "voice.wav");
    writeFileSync(audioPath, new Uint8Array([1, 2, 3]));
    const tool = byName(buildTools({ mode: "local", client: () => client }), "voice_clone_voice");
    const response = await tool.handler({
      name: "Můj hlas",
      reference_text_id: "prompt-cs",
      audio_path: audioPath,
      rights_confirmed: true,
      speaker_relationship: "self",
    });

    expect(calls.createVoice).toHaveBeenCalledWith({
      name: "Můj hlas",
      referenceTextId: "prompt-cs",
      file: expect.any(Buffer),
      rightsAttestation: {
        accepted: true,
        version: "2026-07-22-v1",
        speakerRelationship: "self",
      },
    });
    expect(calls.waitForVoice).toHaveBeenCalledWith(VOICE_ID_A);
    expect(response.structuredContent).toMatchObject({ status: "ready", voice: { id: VOICE_ID_A } });
  });

  it("runs record-and-clone only after prompt selection and confirmation", async () => {
    const { client, calls } = fakeClient();
    const dir = mkdtempSync(join(tmpdir(), "mendelio-mcp-record-test-"));
    const audioPath = join(dir, "recording.wav");
    writeFileSync(audioPath, new Uint8Array([4, 5, 6]));
    const record = vi.fn(async () => ({ ok: true as const, path: audioPath }));
    const tool = byName(
      buildTools({ mode: "local", client: () => client, record }),
      "voice_record_and_clone",
    );

    const choosePrompt = await tool.handler({ name: "Můj hlas" });
    const confirm = await tool.handler({ name: "Můj hlas", reference_text_id: "prompt-cs" });

    expect(choosePrompt.structuredContent).toMatchObject({
      status: "reference_prompt_required",
      prompts: [{ id: "prompt-cs" }],
    });
    expect(confirm.structuredContent).toMatchObject({
      status: "confirmation_required",
      prompt: { id: "prompt-cs" },
    });
    expect(record).not.toHaveBeenCalled();
    expect(calls.createVoice).not.toHaveBeenCalled();

    const rights = await tool.handler({
      name: "Můj hlas",
      reference_text_id: "prompt-cs",
      confirmed: true,
      duration_seconds: 15,
    });

    expect(rights.structuredContent).toMatchObject({
      status: "rights_confirmation_required",
    });
    expect(record).not.toHaveBeenCalled();

    const completed = await tool.handler({
      name: "Můj hlas",
      reference_text_id: "prompt-cs",
      confirmed: true,
      duration_seconds: 15,
      rights_confirmed: true,
      speaker_relationship: "authorized",
    });

    expect(record).toHaveBeenCalledWith(15);
    expect(calls.createVoice).toHaveBeenCalledWith({
      name: "Můj hlas",
      referenceTextId: "prompt-cs",
      file: expect.any(Buffer),
      rightsAttestation: {
        accepted: true,
        version: "2026-07-22-v1",
        speakerRelationship: "authorized",
      },
    });
    expect(calls.waitForVoice).toHaveBeenCalledWith(VOICE_ID_A);
    expect(completed.structuredContent).toMatchObject({
      status: "ready",
      voice: { id: VOICE_ID_A },
    });
  });

  it("stops record-and-clone when the local recorder is unavailable", async () => {
    const { client, calls } = fakeClient();
    const record = vi.fn(async () => ({ ok: false as const, hint: "recorder unavailable" }));
    const tool = byName(
      buildTools({ mode: "local", client: () => client, record }),
      "voice_record_and_clone",
    );
    const response = await tool.handler({
      name: "Můj hlas",
      reference_text_id: "prompt-cs",
      confirmed: true,
      rights_confirmed: true,
      speaker_relationship: "self",
    });

    expect(response.isError).toBe(true);
    expect(response.structuredContent).toMatchObject({
      status: "recorder_unavailable",
      action: "provide_audio_file",
    });
    expect(calls.createVoice).not.toHaveBeenCalled();
  });

  it("marks a completed remote generation without downloadable output as an error", async () => {
    const { client } = fakeClient({
      generation: generation({ output: null }),
    });
    const tool = byName(buildTools({ mode: "remote", client: () => client }), "voice_generate_speech");
    const response = await tool.handler({
      text: "Ahoj",
      voice_version_id: VOICE_ID_A,
    });

    expect(response.isError).toBe(true);
    expect(response.structuredContent).toMatchObject({
      status: "output_unavailable",
      generation: { id: GENERATION_ID, output: null },
    });
  });
});

describe("safe failures", () => {
  it("preserves permission denial as an error without reflecting a credential", async () => {
    const secret = "mvo_do_not_leak";
    const { client, calls } = fakeClient();
    calls.getBalance.mockRejectedValue(
      new VoiceApiError(403, {
        type: "permission_error",
        code: "permission_denied",
        message: `Denied for ${secret}`,
        param: null,
        request_id: "req_safe",
      }),
    );
    const tool = byName(buildTools({ mode: "remote", client: () => client }), "voice_get_balance");
    const response = await tool.handler({});

    expect(response.isError).toBe(true);
    expect(response.structuredContent).toEqual({
      status: "api_error",
      code: "permission_denied",
      action: "grant_required_scope",
      request_id: "req_safe",
    });
    expect(JSON.stringify(response)).not.toContain(secret);
  });

  it("does not reflect unknown thrown error details", async () => {
    const secret = "mv_live_do_not_leak";
    const { client, calls } = fakeClient();
    calls.getBalance.mockRejectedValue(new Error(secret));
    const tool = byName(buildTools({ mode: "remote", client: () => client }), "voice_get_balance");
    const response = await tool.handler({});

    expect(response.isError).toBe(true);
    expect(response.structuredContent).toEqual({
      status: "request_failed",
      action: "retry_or_check_connection",
    });
    expect(JSON.stringify(response)).not.toContain(secret);
  });
});
