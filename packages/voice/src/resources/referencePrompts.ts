import type { MendelioVoice } from "../client.js";
import type { LanguageCode, ListResponse, ReferencePrompt } from "../types.js";

export class ReferencePromptsResource {
  constructor(private readonly client: MendelioVoice) {}

  /** The recording prompts read aloud when cloning a voice, optionally filtered by language. */
  async list(params: { language?: LanguageCode } = {}): Promise<ReferencePrompt[]> {
    const page = await this.client.request<ListResponse<ReferencePrompt>>("GET", "/reference-prompts");
    return params.language ? page.data.filter((p) => p.language === params.language) : page.data;
  }
}
