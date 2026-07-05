// Runtime configuration for the DevMemory MCP client.
//
// The client never touches a database — it only needs the backend URL and an
// API key, both from the environment (set in each AI tool's MCP config).

/** Base URL of the DevMemory REST API (default: local self-host). */
export function host() {
  return (process.env.DEVMEMORY_HOST || "http://localhost:8765").replace(/\/+$/, "");
}

/** Pick the API key from the explicit arg or DEVMEMORY_API_KEY. Throws if absent. */
export function pickKey(argKey) {
  const key = (argKey || process.env.DEVMEMORY_API_KEY || "").trim();
  if (!key) {
    throw new Error("No API key provided. Pass api_key / --api-key or set DEVMEMORY_API_KEY.");
  }
  return key;
}
