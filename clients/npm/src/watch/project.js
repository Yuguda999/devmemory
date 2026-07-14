// Resolve which project a tool conversation belongs to — ported 1:1 from the
// Python daemon's watch/project.py so blocks saved by the Node on-demand sync
// land on the SAME project slug as the Python daemon / hooks / MCP client.

import { execFileSync } from "node:child_process";
import { existsSync, statSync } from "node:fs";
import { basename, dirname, resolve } from "node:path";

import { slugifyName, slugifyRemoteUrl } from "../git.js";
import { readPaused } from "./paused.js";

// Paths under these dirs are tooling noise, not the user's project.
const NOISE = ["/.cursor", "/.config", "/.vscode", "/.codeium", "/node_modules", "/.git/"];

function findGitRoot(startDir) {
  let cur = resolve(startDir);
  for (;;) {
    if (existsSync(`${cur}/.git`)) return cur;
    const parent = dirname(cur);
    if (parent === cur) return null;
    cur = parent;
  }
}

function gitRemote(gitRoot) {
  try {
    const out = execFileSync("git", ["remote", "get-url", "origin"], {
      cwd: gitRoot,
      timeout: 5000,
      stdio: ["ignore", "pipe", "ignore"],
    });
    return out.toString().trim() || null;
  } catch {
    return null;
  }
}

function isDir(p) {
  try {
    return statSync(p).isDirectory();
  } catch {
    return false;
  }
}

function clean(paths) {
  const out = [];
  for (let p of paths) {
    if (typeof p !== "string") continue;
    if (p.startsWith("file://")) p = p.slice("file://".length);
    if (!p.startsWith("/")) continue;
    if (NOISE.some((n) => p.includes(n))) continue;
    out.push(p);
  }
  return out;
}

function mostCommon(counter) {
  let best = null;
  let bestN = -1;
  for (const [k, n] of Object.entries(counter)) {
    if (n > bestN) {
      best = k;
      bestN = n;
    }
  }
  return best;
}

function pickDir(paths) {
  const cleaned = clean(paths);
  if (!cleaned.length) return null;
  // Prefer the git root shared by the most paths.
  const roots = {};
  for (const p of cleaned) {
    const root = findGitRoot(p);
    if (root) roots[root] = (roots[root] || 0) + 1;
  }
  if (Object.keys(roots).length) return mostCommon(roots);
  // No git root: use the most common existing directory.
  const dirs = {};
  for (const p of cleaned) {
    const d = isDir(p) ? p : dirname(p);
    dirs[d] = (dirs[d] || 0) + 1;
  }
  return mostCommon(dirs);
}

function nameFromSlug(slug) {
  return slug.includes("-") ? slug.slice(slug.indexOf("-") + 1) : slug;
}

/**
 * Return { slug, name, remote_url } for a conversation, or null when it can't
 * be tied to a real directory. An explicit remoteUrl (e.g. Codex git_origin_url)
 * wins — it slugs identically to how the server resolves a git remote.
 */
export function resolveConversationProject(paths, fallbackName, remoteUrl) {
  if (remoteUrl) {
    const slug = slugifyRemoteUrl(remoteUrl);
    return { slug, name: nameFromSlug(slug), remote_url: remoteUrl };
  }

  const directory = pickDir(paths || []);
  if (!directory) {
    const name = (fallbackName || "").trim() || "untitled";
    return { slug: `cursor-${slugifyName(name)}`, name, remote_url: null };
  }

  const gitRoot = findGitRoot(directory);
  if (gitRoot) {
    const remote = gitRemote(gitRoot);
    if (remote) {
      const slug = slugifyRemoteUrl(remote);
      return { slug, name: nameFromSlug(slug), remote_url: remote };
    }
    const dn = basename(gitRoot);
    return { slug: slugifyName(dn), name: dn, remote_url: null };
  }

  const dn = basename(directory);
  return { slug: slugifyName(dn), name: dn, remote_url: null };
}

/** Auto-save is ON by default; off globally via env, or per-project via paused.json. */
export function shouldSave(slug) {
  const flag = (process.env.DEVMEMORY_AUTOSAVE || "").trim().toLowerCase();
  if (["off", "0", "false", "no"].includes(flag)) return false;
  return !readPaused().has(slug);
}
