// Client-side project resolution. Ported 1:1 from the Python resolver
// (devmemory/resolver/git_resolver.py) so both clients map the same repo to the
// same project slug.

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";

/** Lowercase, non-[a-z0-9-] → '-', collapse repeats, trim '-'. */
export function slugifyName(name) {
  let s = String(name).toLowerCase().trim();
  s = s.replace(/[^a-z0-9-]/g, "-");
  s = s.replace(/-{2,}/g, "-");
  s = s.replace(/^-+|-+$/g, "");
  return s || "unnamed";
}

function slugifyPathSegments(path) {
  const segs = path.split("/").filter(Boolean);
  let raw;
  if (segs.length >= 2) raw = `${segs[segs.length - 2]}-${segs[segs.length - 1]}`;
  else if (segs.length) raw = segs[0];
  else return "unnamed";
  return slugifyName(raw);
}

/** github.com/user/repo(.git) | git@host:user/repo | https://… → "user-repo". */
export function slugifyRemoteUrl(url) {
  let cleaned = String(url).trim();
  if (cleaned.endsWith(".git")) cleaned = cleaned.slice(0, -4);
  cleaned = cleaned.replace(/\/+$/, "");

  const ssh = cleaned.match(/^[\w.-]+@[\w.-]+:(.+)$/);
  if (ssh) return slugifyPathSegments(ssh[1]);

  cleaned = cleaned.replace(/^https?:\/\//, "");
  const idx = cleaned.indexOf("/");
  const pathPart = idx >= 0 ? cleaned.slice(idx + 1) : cleaned;
  return slugifyPathSegments(pathPart);
}

function findGitRoot(startDir) {
  let cur = resolve(startDir);
  for (;;) {
    if (existsSync(join(cur, ".git"))) return cur;
    const parent = dirname(cur);
    if (parent === cur) return null;
    cur = parent;
  }
}

function gitRemoteUrl(gitRoot) {
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

/**
 * Resolve a working directory to { slug, name, remote_url }.
 * Identity is the project folder name (git root dir, else cwd basename).
 * Priority: explicit → git root dir name → cwd basename.
 *
 * Git-remote slugging was dropped: a flaky remote lookup (git missing/timeout,
 * subdir cwd) forked one repo into two projects (owner-repo vs repo). Folder
 * name is stable within a machine and has no such failure mode.
 */
export function resolveProject(cwd, explicitProject) {
  if (explicitProject) {
    return { slug: slugifyName(explicitProject), name: explicitProject, remote_url: null };
  }

  const cwdPath = resolve(cwd);
  const gitRoot = findGitRoot(cwdPath);
  const dirName = basename(gitRoot || cwdPath) || "unnamed";
  return { slug: slugifyName(dirName), name: dirName, remote_url: null };
}
