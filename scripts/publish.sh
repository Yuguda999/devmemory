#!/usr/bin/env bash
#
# publish.sh — build and publish DevMemory to PyPI and npm.
#
# The Python package uses the `uv_build` backend, so `uv` is required to build
# it (plain `python -m build` will not work). This script bootstraps `uv` via
# pipx if it is missing, builds the wheel + sdist, and publishes both the
# Python and npm packages.
#
# Usage:
#   scripts/publish.sh                 # build + publish both (asks to confirm)
#   scripts/publish.sh --dry-run       # build both, publish nothing
#   scripts/publish.sh --python-only   # only the PyPI package
#   scripts/publish.sh --npm-only      # only the npm package
#   scripts/publish.sh --yes           # skip the confirmation prompt
#
# Credentials (set before running, or you will be prompted / it will fail):
#   PyPI : export UV_PUBLISH_TOKEN=pypi-...        (a PyPI API token)
#   npm  : run `npm login` once beforehand
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DRY_RUN=0
DO_PY=1
DO_NPM=1
ASSUME_YES=0

for arg in "$@"; do
  case "$arg" in
    --dry-run)     DRY_RUN=1 ;;
    --python-only) DO_NPM=0 ;;
    --npm-only)    DO_PY=0 ;;
    --yes|-y)      ASSUME_YES=1 ;;
    *) echo "Unknown flag: $arg" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!  %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m✗  %s\033[0m\n' "$*" >&2; exit 1; }

# ── Version sanity: pyproject and npm must agree ────────────────────────────
PY_VER="$(grep -m1 '^version' pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/')"
NPM_VER="$(grep -m1 '"version"' clients/npm/package.json | sed -E 's/.*"([^"]+)".*/\1/')"
say "Python version: $PY_VER    npm version: $NPM_VER"
[ "$PY_VER" = "$NPM_VER" ] || warn "pyproject ($PY_VER) and npm ($NPM_VER) versions differ."

# ── Warn on a dirty tree ────────────────────────────────────────────────────
if [ -n "$(git status --porcelain)" ]; then
  warn "Working tree has uncommitted changes:"
  git status --short
fi

if [ "$DRY_RUN" -eq 0 ] && [ "$ASSUME_YES" -eq 0 ]; then
  printf '\nPublish v%s to %s? [y/N] ' "$PY_VER" \
    "$([ $DO_PY = 1 ] && printf 'PyPI '; [ $DO_NPM = 1 ] && printf 'npm')"
  read -r reply
  case "$reply" in y|Y|yes|YES) ;; *) die "Aborted." ;; esac
fi

# ── Python: build with uv, publish with uv ──────────────────────────────────
if [ "$DO_PY" -eq 1 ]; then
  if ! command -v uv >/dev/null 2>&1; then
    say "uv not found — installing via pipx"
    command -v pipx >/dev/null 2>&1 || die "pipx not found. Install uv manually: https://docs.astral.sh/uv/"
    pipx install uv
    # pipx installs into ~/.local/bin; make sure it is reachable this run.
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || die "uv still not on PATH after install. Add ~/.local/bin to PATH."
  fi

  say "Cleaning dist/"
  rm -rf dist
  say "Building Python package (uv build)"
  uv build
  ls -la dist

  if [ "$DRY_RUN" -eq 1 ]; then
    warn "Dry run — skipping PyPI upload."
  else
    # PyPI no longer accepts username/password — an API token is required.
    # Accept it from UV_PUBLISH_TOKEN or PYPI_TOKEN; otherwise prompt (hidden).
    TOKEN="${UV_PUBLISH_TOKEN:-${PYPI_TOKEN:-}}"
    if [ -z "$TOKEN" ]; then
      warn "No PyPI API token in UV_PUBLISH_TOKEN / PYPI_TOKEN."
      warn "Create one at https://pypi.org/manage/account/token/ (starts with 'pypi-')."
      printf 'Paste PyPI API token: '
      read -rs TOKEN
      printf '\n'
    fi
    [ -n "$TOKEN" ] || die "No token provided."
    case "$TOKEN" in
      pypi-*) ;;
      *) warn "Token does not start with 'pypi-' — that is usually wrong." ;;
    esac
    say "Publishing to PyPI (uv publish, token auth)"
    # `--token` is the token-auth shortcut (equivalent to username __token__).
    uv publish --token "$TOKEN"
  fi
fi

# ── npm ─────────────────────────────────────────────────────────────────────
if [ "$DO_NPM" -eq 1 ]; then
  command -v npm >/dev/null 2>&1 || die "npm not found."
  pushd clients/npm >/dev/null
  if [ "$DRY_RUN" -eq 1 ]; then
    say "npm publish --dry-run"
    npm publish --dry-run --access public
  else
    npm whoami >/dev/null 2>&1 || die "Not logged in to npm. Run: npm login"
    say "Publishing to npm"
    npm publish --access public
  fi
  popd >/dev/null
fi

say "Done."
