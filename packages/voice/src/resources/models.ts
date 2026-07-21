import type { MendelioVoice } from "../client.js";
import type { ListResponse, Model } from "../types.js";

export class ModelsResource {
  constructor(private readonly client: MendelioVoice) {}

  /** List supported models (provider-neutral capabilities). */
  async list(): Promise<Model[]> {
    const page = await this.client.request<ListResponse<Model>>("GET", "/models");
    return page.data;
  }

  /** Get one model by id. */
  get(id: string): Promise<Model> {
    return this.client.request<Model>("GET", `/models/${encodeURIComponent(id)}`);
  }
}
