import type { MendelioVoice } from "../client.js";
import type { Balance } from "../types.js";

export class BalanceResource {
  constructor(private readonly client: MendelioVoice) {}

  /** Your credit balance in whole audio seconds (total = reserved + available). */
  get(): Promise<Balance> {
    return this.client.request<Balance>("GET", "/balance");
  }
}
