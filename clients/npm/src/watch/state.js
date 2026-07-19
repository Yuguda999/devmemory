// Watermark persistence — mirrors the Python daemon's WatchState.
//
// Tracks, per conversation, how many messages have already been saved and which
// DevMemory session they landed in, so a re-scan never re-saves old turns and
// every turn of one conversation stays in the same session. Stored at
// ~/.devmemory/watch_state.json in the SAME format the Python daemon uses, so
// the two clients share one watermark and never double-save each other's work.

import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

const STATE_PATH = join(homedir(), ".devmemory", "watch_state.json");

export class WatchState {
  constructor(path = STATE_PATH) {
    this.path = path;
    this._data = { conversations: {} };
    try {
      const parsed = JSON.parse(readFileSync(this.path, "utf8"));
      if (parsed && typeof parsed === "object") {
        this._data = parsed;
        if (!this._data.conversations || typeof this._data.conversations !== "object") {
          this._data.conversations = {};
        }
      }
    } catch {
      /* missing / corrupt → empty (safe: at worst re-save recent turns once) */
    }
  }

  savedCount(key) {
    const entry = this._data.conversations[key];
    return entry && Number.isFinite(entry.saved_count) ? Number(entry.saved_count) : 0;
  }

  sessionId(key) {
    const entry = this._data.conversations[key];
    return (entry && entry.session_id) || null;
  }

  record(key, savedCount, sessionId) {
    const entry = this._data.conversations[key] || {};
    entry.saved_count = savedCount;
    if (sessionId) entry.session_id = sessionId;
    this._data.conversations[key] = entry;
  }

  save() {
    mkdirSync(dirname(this.path), { recursive: true });
    const tmp = `${this.path}.tmp`;
    writeFileSync(tmp, `${JSON.stringify(this._data, null, 2)}\n`, "utf8");
    renameSync(tmp, this.path);
  }
}
