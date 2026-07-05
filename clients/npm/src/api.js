// Thin HTTP client for the DevMemory REST API. Mirrors the Python client's
// `_api` helper: returns parsed JSON on success, or an {ok:false, error} object
// on any failure (missing key, network error, non-2xx) so callers return it
// verbatim.

import { host, pickKey } from "./config.js";

// Generous timeout: managed free tiers (Render/Fly) cold-start ~30-50s when idle.
const TIMEOUT_MS = 60_000;

export async function apiCall(method, path, { apiKey, json, params } = {}) {
  let key;
  try {
    key = pickKey(apiKey);
  } catch (e) {
    return { ok: false, error: e.message };
  }

  let url = host() + path;
  if (params) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null) q.set(k, String(v));
    }
    const s = q.toString();
    if (s) url += "?" + s;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let resp;
  try {
    resp = await fetch(url, {
      method,
      headers: {
        "X-API-Key": key,
        ...(json ? { "content-type": "application/json" } : {}),
      },
      body: json ? JSON.stringify(json) : undefined,
      signal: controller.signal,
    });
  } catch (e) {
    return {
      ok: false,
      error: `Could not reach DevMemory at ${host()} (${e.message}). ` +
        "Set DEVMEMORY_HOST, or start the server with `devmemory --rest`.",
    };
  } finally {
    clearTimeout(timer);
  }

  if (!resp.ok) {
    let detail;
    try {
      detail = (await resp.json())?.detail;
    } catch {
      /* non-JSON error body */
    }
    return { ok: false, error: detail || `HTTP ${resp.status}` };
  }

  try {
    return await resp.json();
  } catch {
    return { ok: false, error: "Invalid (non-JSON) response from the DevMemory server" };
  }
}
