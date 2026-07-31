import assert from "node:assert/strict";

const base = process.env.MENDELIO_VOICE_OPENAPI_URL ?? "https://api.mendelio.net/openapi.json";
const url = new URL(base);
url.searchParams.set("cb", `${Date.now()}-${Math.random()}`);
const response = await fetch(url, {
  headers: { "cache-control": "no-cache", accept: "application/json" },
});
assert.equal(response.status, 200, `OpenAPI returned HTTP ${response.status}`);
const document = await response.json();

assert.equal(document.openapi, "3.1.0");
assert.equal(document.servers?.[0]?.url, "https://api.mendelio.net");

const operations = [
  ["post", "/v1/audio/speech/jobs"],
  ["get", "/v1/audio/speech/jobs/{speechJobId}"],
  ["get", "/v1/audio/balance"],
  ["get", "/v1/audio/models"],
  ["get", "/v1/audio/models/{modelId}"],
  ["get", "/v1/audio/reference-prompts"],
  ["get", "/v1/audio/voices"],
  ["get", "/v1/audio/voices/{voiceVersionId}"],
  ["get", "/v1/audio/owned-voices"],
  ["post", "/v1/audio/owned-voices"],
  ["get", "/v1/audio/owned-voices/{voiceVersionId}"],
  ["post", "/v1/audio/owned-voices/{voiceVersionId}/submit"],
];
for (const [method, path] of operations) {
  assert.ok(document.paths?.[path]?.[method], `Missing ${method.toUpperCase()} ${path}`);
}

for (const retiredPath of ["/v1/voice/generate", "/v1/audio/generate", "/v1/audio/generations/{id}"]) {
  assert.equal(document.paths?.[retiredPath], undefined, `Retired path returned: ${retiredPath}`);
}

const schemas = document.components?.schemas;
assert.ok(schemas, "OpenAPI components.schemas is missing");
const schema = (name) => {
  assert.ok(schemas[name], `Missing schema ${name}`);
  return schemas[name];
};

assert.deepEqual(
  [...schema("SpeechSynthesisRequest").required].sort(),
  ["text", "voiceVersionId"],
);
assert.equal(schema("SpeechSynthesisRequest").additionalProperties, false);
assert.ok(schema("SpeechSynthesisRequest").properties.store);
assert.equal(schema("SpeechSynthesisRequest").properties.retentionDays, undefined);
assert.equal(schema("SpeechSynthesisRequest").properties.inputNormalization, undefined);

assert.ok(schema("CreateVoiceRequest").required.includes("rightsAttestation"));
assert.deepEqual(
  schema("CreateVoiceRequest").properties.rightsAttestation.properties.version.enum,
  ["2026-07-22-v1"],
);
assert.deepEqual(
  schema("CreateVoiceRequest").properties.rightsAttestation.properties.speakerRelationship.enum,
  ["self", "authorized"],
);

assert.deepEqual(
  [...schema("VoiceCatalogPage").required].sort(),
  ["data", "etag", "hasMore", "nextCursor", "revision"].sort(),
);
assert.deepEqual(
  [...schema("CatalogVoice").required].sort(),
  [
    "accessClass",
    "availability",
    "avatarLightUrl",
    "avatarUrl",
    "capabilities",
    "categoryTags",
    "description",
    "displayName",
    "languageCode",
    "personaName",
    "preview",
    "publicId",
    "relation",
    "styleTags",
    "useCaseTags",
    "voiceVersionId",
  ].sort(),
);

const generationStates = [
  "queued",
  "preparing_capacity",
  "generating",
  "encoding",
  "completed",
  "failed",
  "cancelling",
  "cancelled",
];
assert.deepEqual(schema("ReadSpeechJob").properties.state.enum, generationStates);
assert.deepEqual(schema("WebhookSpeechJobData").properties.state.enum, generationStates);
assert.deepEqual(schema("ReadSpeechJob").properties.object.enum, ["audio.speech_job"]);

const errorCodes = schema("ErrorEnvelope").properties.error.properties.code.enum;
for (const code of [
  "authentication_required",
  "permission_denied",
  "invalid_request",
  "idempotency_conflict",
  "voice_not_found",
  "voice_not_ready",
  "insufficient_credit",
  "rate_limited",
  "queue_limit_reached",
  "generation_not_completed",
  "generation_terminal",
  "capacity_saturated",
  "capacity_unavailable",
  "internal_error",
]) {
  assert.ok(errorCodes.includes(code), `Missing error code ${code}`);
}

const webhookTypes = schema("WebhookEnvelope").anyOf.flatMap(
  (branch) => branch.properties.type.enum,
);
assert.deepEqual(webhookTypes, [
  "speech_job.completed",
  "speech_job.failed",
  "speech_job.cancelled",
  "voice.ready",
  "voice.failed",
  "transcription.completed",
  "transcription.failed",
  "transcription.expired",
]);

process.stdout.write(`live OpenAPI contract passed (${operations.length} SDK operations)\n`);
