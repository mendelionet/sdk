import { spawn } from "node:child_process";
import { hostname } from "node:os";
import { writeCredentials } from "./credentials.js";

const DEFAULT_API = "https://api.mendelio.net";
const DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code";
export const MENDELIO_VOICE_CLI_CLIENT_ID = "mendelio-voice-cli";
export const MENDELIO_VOICE_MCP_CLIENT_ID = "mendelio-voice-mcp";

export interface DeviceLoginOptions {
  /** Defaults to https://api.mendelio.net, whose OAuth metadata declares the device and token endpoints. */
  apiBaseUrl?: string;
  /** Registered public client. Defaults to the official Mendelio Voice CLI. */
  clientId?: string;
  /** Open the verification URL in a browser. Default true (ignored when there is no GUI). */
  openBrowser?: boolean;
  /** Called with the code + URL as soon as the device flow begins, so a CLI can print them. */
  onCode?: (info: { userCode: string; verificationUri: string; verificationUriComplete: string }) => void;
  fetch?: typeof fetch;
}

interface DeviceCodeResponse {
  device_code: string;
  user_code: string;
  verification_uri: string;
  verification_uri_complete: string;
  expires_in: number;
  interval: number;
}

interface AuthorizationServerMetadata {
  issuer: string;
  token_endpoint: string;
  device_authorization_endpoint: string;
}

/**
 * The OAuth 2.0 Device Authorization flow, shared by the CLI and the MCP server. Begins a grant,
 * surfaces the code + URL, opens the browser, polls the token endpoint respecting `interval` and
 * `slow_down`, and on approval stores the returned API key. Resolves with the key prefix.
 */
export async function deviceLogin(options: DeviceLoginOptions = {}): Promise<{ keyPrefix: string }> {
  const api = (options.apiBaseUrl ?? DEFAULT_API).replace(/\/$/, "");
  const doFetch = options.fetch ?? globalThis.fetch;
  const clientId = options.clientId ?? MENDELIO_VOICE_CLI_CLIENT_ID;

  const metadataResponse = await doFetch(`${api}/.well-known/oauth-authorization-server`);
  if (!metadataResponse.ok) throw new Error(`OAuth metadata discovery failed (HTTP ${metadataResponse.status}).`);
  const metadata = (await metadataResponse.json()) as Partial<AuthorizationServerMetadata>;
  const apiOrigin = new URL(api).origin;
  if (
    metadata.issuer !== api ||
    typeof metadata.device_authorization_endpoint !== "string" ||
    typeof metadata.token_endpoint !== "string" ||
    new URL(metadata.device_authorization_endpoint).origin !== apiOrigin ||
    new URL(metadata.token_endpoint).origin !== apiOrigin
  ) {
    throw new Error("OAuth metadata does not describe the configured API origin.");
  }

  const begin = await doFetch(metadata.device_authorization_endpoint, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: clientId, label: hostLabel() }),
  });
  if (!begin.ok) throw new Error(`Device authorization failed (HTTP ${begin.status}).`);
  const grant = (await begin.json()) as DeviceCodeResponse;

  options.onCode?.({
    userCode: grant.user_code,
    verificationUri: grant.verification_uri,
    verificationUriComplete: grant.verification_uri_complete,
  });
  if (options.openBrowser !== false) openBrowser(grant.verification_uri_complete);

  const deadline = Date.now() + grant.expires_in * 1000;
  let intervalMs = Math.max(grant.interval, 1) * 1000;
  while (Date.now() < deadline) {
    await sleep(intervalMs);
    const res = await doFetch(metadata.token_endpoint, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: DEVICE_GRANT,
        device_code: grant.device_code,
        client_id: clientId,
      }),
    });
    const json = (await res.json().catch(() => ({}))) as { access_token?: string; error?: string };
    if (json.access_token) {
      const apiKey = json.access_token;
      const keyPrefix = apiKey.slice(0, 12);
      writeCredentials({ api_key: apiKey, key_prefix: keyPrefix, created_at: new Date().toISOString() });
      return { keyPrefix };
    }
    if (json.error === "slow_down") intervalMs += 5_000;
    else if (json.error && json.error !== "authorization_pending") {
      throw new Error(`Login failed: ${json.error}`);
    }
  }
  throw new Error("Login timed out before it was approved.");
}

function hostLabel(): string {
  try {
    return `mendelio-voice on ${hostname()}`;
  } catch {
    return "mendelio-voice";
  }
}

function openBrowser(url: string): void {
  const cmd = process.platform === "darwin" ? "open" : process.platform === "win32" ? "start" : "xdg-open";
  try {
    const child = spawn(cmd, [url], { stdio: "ignore", detached: true, shell: process.platform === "win32" });
    child.on("error", () => {});
    child.unref();
  } catch {
    // no browser available — the printed URL is the fallback
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
