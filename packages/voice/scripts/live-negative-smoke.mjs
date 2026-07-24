import assert from "node:assert/strict";
import { AuthenticationError, MendelioVoice } from "../dist/index.js";

const apiKey = `mv_live_${"C".repeat(43)}`;
const client = new MendelioVoice({
  apiKey,
  maxRetries: 0,
  timeoutMs: 15_000,
});
const id = "00000000-0000-4000-8000-000000000001";

const operations = [
  ["balance.get", () => client.balance.get()],
  ["models.list", () => client.models.list()],
  ["models.get", () => client.models.get("mendelio-voice-1")],
  ["referencePrompts.list", () => client.referencePrompts.list({ language: "cs" })],
  ["voices.page", () => client.voices.page({ language: "cs", limit: 1 })],
  ["voices.get", () => client.voices.get(id)],
  ["voices.getOwned", () => client.voices.getOwned(id)],
  ["voices.create", () => client.voices.create({
    name: "Auth probe",
    referenceTextId: "cs-2026-06c",
    rightsAttestation: {
      accepted: true,
      version: "2026-07-22-v1",
      speakerRelationship: "self",
    },
  })],
  ["voices.submit", () => client.voices.submit(id)],
  ["generations.create", () => client.generations.create({
    text: "Auth probe",
    voiceVersionId: id,
  })],
  ["generations.get", () => client.generations.get(id)],
];

for (const [name, operation] of operations) {
  let error;
  try {
    await operation();
  } catch (cause) {
    error = cause;
  }
  assert.ok(error instanceof AuthenticationError, `${name} did not return AuthenticationError`);
  assert.equal(error.code, "authentication_required", `${name} returned ${error.code}`);
  assert.ok(!error.message.includes(apiKey), `${name} reflected the bearer token`);
}

process.stdout.write(`live SDK routing and authentication passed (${operations.length} operations)\n`);
