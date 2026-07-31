import { readFileSync } from "node:fs";
import type { GenerateParams, LanguageCode } from "mendelio-voice";
import { MendelioVoice } from "mendelio-voice";
import type { LocalVoiceMcpOperations } from "./core.js";

/** Mechanical local adapter. All HTTP and filesystem behavior stays outside the shared core. */
export class MendelioVoiceSdkOperations implements LocalVoiceMcpOperations {
  constructor(private readonly client: MendelioVoice) {}

  async listVoices() {
    const voices = [];
    for await (const voice of this.client.voices.list()) voices.push(voice);
    return voices;
  }

  createGeneration(params: GenerateParams) {
    return this.client.generations.create(params);
  }

  waitForGeneration(id: string) {
    return this.client.generations.waitFor(id);
  }

  getGeneration(id: string) {
    return this.client.generations.get(id);
  }

  getBalance() {
    return this.client.balance.get();
  }

  listReferencePrompts(params: { language?: LanguageCode } = {}) {
    return this.client.referencePrompts.list(params);
  }

  synthesizeAndDownload(params: GenerateParams) {
    return this.client.speak(params);
  }

  async cloneVoiceFromFile(args: {
    name: string;
    referenceTextId: string;
    audioPath: string;
    speakerRelationship: "self" | "authorized";
  }) {
    const voice = await this.client.voices.createFromFile({
      name: args.name,
      referenceTextId: args.referenceTextId,
      file: readFileSync(args.audioPath),
      rightsAttestation: {
        accepted: true,
        version: "2026-07-22-v1",
        speakerRelationship: args.speakerRelationship,
      },
    });
    return this.client.voices.waitForReady(voice.id);
  }
}
