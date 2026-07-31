#!/usr/bin/env node
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const packageRoot = fileURLToPath(new URL("../", import.meta.url));
const voicePackagePath = fileURLToPath(new URL("../../voice/package.json", import.meta.url));
const identityPath = fileURLToPath(new URL("../../voice/src/identity.json", import.meta.url));
const packagePath = fileURLToPath(new URL("../package.json", import.meta.url));
const serverPath = fileURLToPath(new URL("../server.json", import.meta.url));
const versionPath = fileURLToPath(new URL("../src/version.ts", import.meta.url));
const write = process.argv.includes("--write");

if (!write && !process.argv.includes("--check")) {
  throw new Error("Usage: sync-metadata.mjs --check|--write");
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

const packageJson = readJson(packagePath);
const voicePackageJson = readJson(voicePackagePath);
const identity = readJson(identityPath);
const serverJson = readJson(serverPath);
const expectedRegistryName = identity.technical.registryName;
const expectedVersionSource = `// Generated from package.json by scripts/sync-metadata.mjs.\n// Do not edit this value by hand.\nexport const MENDELIO_VOICE_MCP_VERSION = ${JSON.stringify(packageJson.version)};\n`;

if (packageJson.mcpName !== expectedRegistryName) {
  throw new Error(`package.json mcpName must be ${expectedRegistryName}`);
}
if (serverJson.name !== expectedRegistryName) {
  throw new Error(`server.json name must be ${expectedRegistryName}`);
}
if (voicePackageJson.version !== packageJson.version) {
  throw new Error(
    `Lockstep SDK versions differ: mendelio-voice=${voicePackageJson.version}, mendelio-voice-mcp=${packageJson.version}`,
  );
}

const npmPackage = serverJson.packages?.find(
  (candidate) => candidate.registryType === "npm" && candidate.identifier === packageJson.name,
);
if (!npmPackage) {
  throw new Error(`server.json must reference npm package ${packageJson.name}`);
}
if (!serverJson.remotes?.some(
  (candidate) => candidate.type === "streamable-http" && candidate.url === identity.urls.mcp,
)) {
  throw new Error("server.json must reference the canonical Mendelio Voice remote MCP endpoint");
}

const synchronizedServer = {
  ...serverJson,
  name: identity.technical.registryName,
  title: identity.mcp.displayName,
  description: identity.mcp.description,
  version: packageJson.version,
  remotes: [{ type: "streamable-http", url: identity.urls.mcp }],
  packages: serverJson.packages.map((candidate) =>
    candidate === npmPackage ? { ...candidate, version: packageJson.version } : candidate,
  ),
};
const expectedServerSource = `${JSON.stringify(synchronizedServer, null, 2)}\n`;

const synchronizedPackage = {
  ...packageJson,
  description: identity.mcp.packageDescription,
  mcpName: identity.technical.registryName,
  homepage: identity.urls.developers,
};
const expectedPackageSource = `${JSON.stringify(synchronizedPackage, null, 2)}\n`;

if (write) {
  writeFileSync(versionPath, expectedVersionSource);
  writeFileSync(serverPath, expectedServerSource);
  writeFileSync(packagePath, expectedPackageSource);
  process.stdout.write(`Synchronized Mendelio Voice MCP metadata at ${packageJson.version}\n`);
} else {
  const drift = [];
  if (readFileSync(versionPath, "utf8") !== expectedVersionSource) drift.push("src/version.ts");
  if (readFileSync(serverPath, "utf8") !== expectedServerSource) drift.push("server.json");
  if (JSON.stringify(packageJson) !== JSON.stringify(synchronizedPackage)) drift.push("package.json");
  if (drift.length) {
    throw new Error(
      `Mendelio Voice MCP metadata drifted in ${drift.join(", ")}; run node ${packageRoot}scripts/sync-metadata.mjs --write`,
    );
  }
  process.stdout.write(`Mendelio Voice MCP metadata is synchronized at ${packageJson.version}\n`);
}
