// Per-project pause list — reads ~/.devmemory/paused.json, the SAME file the
// Python client's `should_save` consults, so `devmemory stop` in either client
// pauses auto-save consistently.

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const PAUSED_PATH = join(homedir(), ".devmemory", "paused.json");

/** Returns a Set of project slugs the user has explicitly paused. */
export function readPaused() {
  try {
    const data = JSON.parse(readFileSync(PAUSED_PATH, "utf8"));
    if (Array.isArray(data)) return new Set(data.filter((s) => typeof s === "string"));
  } catch {
    /* missing / corrupt → nothing paused */
  }
  return new Set();
}
