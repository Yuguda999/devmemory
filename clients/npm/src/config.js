// Runtime configuration for the DevMemory MCP client.
//
// Resolution order mirrors the Python client, so both read the same setup:
//   host:    DEVMEMORY_HOST env → ~/.devmemory/config.json → default
//   api key: explicit arg → DEVMEMORY_API_KEY env → ~/.devmemory/api_key → config.json

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

import { readConfig } from "./store.js";

/** Base URL of the DevMemory REST API (default: local self-host). */
export function host() {
  return (process.env.DEVMEMORY_HOST || readConfig().host || "http://localhost:8765").replace(
    /\/+$/,
    "",
  );
}

/** Pick the API key from arg → env → key file → config. Throws if absent. */
export function pickKey(argKey) {
  let key = (argKey || process.env.DEVMEMORY_API_KEY || "").trim();
  if (!key) {
    try {
      key = readFileSync(join(homedir(), ".devmemory", "api_key"), "utf8").trim();
    } catch {
      /* no key file */
    }
  }
  if (!key) key = (readConfig().api_key || "").trim();
  if (!key) {
    throw new Error("No API key provided. Pass api_key / --api-key or set DEVMEMORY_API_KEY.");
  }
  return key;
}
