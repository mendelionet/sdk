import type { MendelioVoice } from "../client.js";
import type { ListResponse, Model } from "../types.js";
import { InvalidRequestError } from "../errors.js";

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

  /**
   * Resolve an exact id, a moving alias such as `soniox`, or the current default.
   * Resolution is catalogue-driven, so a new model version needs no SDK release.
   */
  async resolve(selector?: string | null): Promise<Model> {
    const models = await this.list();
    const model = selector
      ? models.find((candidate) => candidate.id === selector || candidate.aliases.includes(selector))
      : models.find((candidate) => candidate.default);
    if (model) return model;
    throw new InvalidRequestError(400, {
      type: "invalid_request_error",
      code: "invalid_request",
      message: selector ? `Unknown voice model selector: ${selector}` : "The model catalogue has no default.",
      param: "model",
      request_id: "",
    });
  }
}
