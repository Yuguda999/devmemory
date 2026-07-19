import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { apiCall } from "../src/api.js";
import { resolveProject, slugifyName, slugifyRemoteUrl } from "../src/git.js";

// ── Slug parity with the Python resolver ────────────────────────────────────

test("slugifyRemoteUrl: https + .git", () => {
  assert.equal(slugifyRemoteUrl("https://github.com/User/My_Repo.git"), "user-my-repo");
});

test("slugifyRemoteUrl: ssh", () => {
  assert.equal(slugifyRemoteUrl("git@github.com:Owner/Repo.git"), "owner-repo");
});

test("slugifyRemoteUrl: trailing slash + subgroup", () => {
  assert.equal(slugifyRemoteUrl("https://gitlab.com/team/group/proj/"), "group-proj");
});

test("slugifyName: punctuation collapses", () => {
  assert.equal(slugifyName("My Cool Project!!"), "my-cool-project");
});

test("resolveProject: explicit override", () => {
  const p = resolveProject("/tmp/whatever", "Explicit Name");
  assert.equal(p.slug, "explicit-name");
  assert.equal(p.name, "Explicit Name");
  assert.equal(p.remote_url, null);
});

test("resolveProject: non-git dir falls back to basename", () => {
  const p = resolveProject("/tmp/nonexistent-dir-xyz-123");
  assert.equal(p.slug, "nonexistent-dir-xyz-123");
});

// ── API error mapping (no network) ──────────────────────────────────────────

test("apiCall: missing key returns {ok:false}", async () => {
  // Isolate HOME to an empty dir so the ~/.devmemory/api_key + config.json
  // fallbacks in config.js find nothing — otherwise a real local key leaks in.
  const prevHome = process.env.HOME;
  const prevUserProfile = process.env.USERPROFILE;
  const empty = mkdtempSync(join(tmpdir(), "dm-nohome-"));
  process.env.HOME = empty;
  process.env.USERPROFILE = empty;
  delete process.env.DEVMEMORY_API_KEY;
  try {
    const r = await apiCall("GET", "/projects", {});
    assert.equal(r.ok, false);
    assert.match(r.error, /API key/i);
  } finally {
    if (prevHome === undefined) delete process.env.HOME;
    else process.env.HOME = prevHome;
    if (prevUserProfile === undefined) delete process.env.USERPROFILE;
    else process.env.USERPROFILE = prevUserProfile;
  }
});
