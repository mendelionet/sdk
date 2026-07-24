import assert from "node:assert/strict";

const origin = process.env.MENDELIO_VOICE_API_ORIGIN ?? "https://api.mendelio.net";
const cacheBust = () => `cb=${Date.now()}-${Math.random()}`;
const scopes = [
  "balance:read",
  "voices:read",
  "voices:write",
  "speech:read",
  "speech:write",
  "transcriptions:read",
  "transcriptions:write",
];

async function json(path, init) {
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(`${origin}${path}${separator}${cacheBust()}`, {
    ...init,
    headers: {
      "cache-control": "no-cache",
      accept: "application/json, text/event-stream",
      ...(init?.headers ?? {}),
    },
  });
  const text = await response.text();
  let body;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  return { response, body, text };
}

const protectedResource = await json("/.well-known/oauth-protected-resource");
assert.equal(protectedResource.response.status, 200);
assert.equal(protectedResource.body.resource, origin);
assert.deepEqual(protectedResource.body.authorization_servers, [origin]);
assert.deepEqual(protectedResource.body.scopes_supported, scopes);

const authorizationServer = await json("/.well-known/oauth-authorization-server");
assert.equal(authorizationServer.response.status, 200);
assert.equal(authorizationServer.body.issuer, origin);
assert.equal(authorizationServer.body.authorization_endpoint, `${origin}/oauth/authorize`);
assert.equal(authorizationServer.body.token_endpoint, `${origin}/oauth/token`);
assert.equal(authorizationServer.body.registration_endpoint, `${origin}/oauth/register`);
assert.equal(authorizationServer.body.device_authorization_endpoint, `${origin}/v1/device/code`);
assert.ok(authorizationServer.body.grant_types_supported.includes("authorization_code"));
assert.ok(authorizationServer.body.code_challenge_methods_supported.includes("S256"));
assert.deepEqual(authorizationServer.body.scopes_supported, scopes);

const initialize = {
  jsonrpc: "2.0",
  id: 1,
  method: "initialize",
  params: {
    protocolVersion: "2025-06-18",
    capabilities: {},
    clientInfo: { name: "mendelio-remote-auth-smoke", version: "1.0.0" },
  },
};
const expectedChallenge =
  `Bearer resource_metadata="${origin}/.well-known/oauth-protected-resource"`;

for (const method of ["POST", "GET", "DELETE"]) {
  const result = await json("/mcp", {
    method,
    ...(method === "POST"
      ? { headers: { "content-type": "application/json" }, body: JSON.stringify(initialize) }
      : {}),
  });
  assert.equal(result.response.status, 401, `${method} /mcp must challenge`);
  assert.equal(result.response.headers.get("www-authenticate"), expectedChallenge);
  assert.equal(result.response.headers.get("cache-control"), "no-store");
}

const fakeTokens = [
  `mv_live_${"A".repeat(43)}`,
  `mvo_${"B".repeat(43)}`,
];
for (const token of fakeTokens) {
  for (const [path, init] of [
    ["/v1/audio/balance", { method: "GET" }],
    ["/mcp", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(initialize),
    }],
  ]) {
    const result = await json(path, {
      ...init,
      headers: { ...(init.headers ?? {}), authorization: `Bearer ${token}` },
    });
    assert.equal(result.response.status, 401, `${path} must reject an unknown bearer`);
    assert.ok(!result.text.includes(token), `${path} reflected a bearer token`);
  }
}

const anonymousBalance = await json("/v1/audio/balance");
assert.equal(anonymousBalance.response.status, 401);
assert.equal(anonymousBalance.body?.error?.code, "authentication_required");

const retiredBase = await json("/v1/voice/balance");
assert.equal(retiredBase.response.status, 404);

const invalidRegistration = await json("/oauth/register", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    client_name: "invalid-smoke-client",
    redirect_uris: ["javascript:alert(1)"],
  }),
});
assert.equal(invalidRegistration.response.status, 400);
assert.equal(invalidRegistration.body?.error, "invalid_redirect_uri");
assert.equal(invalidRegistration.body?.error_description?.includes("redirect_uris"), true);

for (const tokenRequest of [
  {
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ grant_type: "authorization_code" }),
  },
  {
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "not-supported" }).toString(),
  },
]) {
  const result = await json("/oauth/token", { method: "POST", ...tokenRequest });
  assert.equal(result.response.status, 400);
  assert.equal(result.body?.error, "unsupported_grant_type");
  assert.equal(result.body?.error_description, undefined);
}

process.stdout.write(
  "production OAuth discovery/errors, MCP challenge, anti-oracle auth, and retired route passed\n",
);
