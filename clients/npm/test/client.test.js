import assert from "node:assert/strict";
import { test } from "node:test";

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
  delete process.env.DEVMEMORY_API_KEY;
  const r = await apiCall("GET", "/projects", {});
  assert.equal(r.ok, false);
  assert.match(r.error, /API key/i);
});
