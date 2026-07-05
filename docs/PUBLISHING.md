# Publishing `devmemory-ai` to PyPI

The client is distributed on PyPI as **`devmemory-ai`** (the name `devmemory` is
taken by an unrelated project). The import package and CLI command stay
`devmemory`, so users run `devmemory …` after installing `devmemory-ai`.

Releases are automated via **PyPI Trusted Publishing** (OIDC) — no API tokens are
stored. Publishing the wheel + sdist happens in
[`.github/workflows/publish.yml`](../.github/workflows/publish.yml) whenever you
publish a GitHub Release.

## One-time setup (once, ~2 min)

Tell PyPI to trust releases coming from this repo's workflow. On
https://pypi.org (logged in) → avatar → **Your projects** isn't needed yet →
go to **Account settings → Publishing → Add a pending publisher**, and fill in
**exactly**:

| Field | Value |
|-------|-------|
| PyPI Project Name | `devmemory-ai` |
| Owner | `Yuguda999` |
| Repository name | `devmemory` |
| Workflow name | `publish.yml` |
| Environment name | *(leave blank)* |

Click **Add**. No tokens, no GitHub settings — done.

## Cutting a release

1. Bump `version` in `pyproject.toml` (e.g. `0.1.0` → `0.1.1`) and update
   `CHANGELOG.md`. Commit + push.
2. Tag it and create a GitHub Release:
   ```
   git tag v0.1.0 && git push origin v0.1.0
   ```
   Then GitHub → **Releases → Draft a new release** → pick the tag → **Publish**.
3. The `Publish to PyPI` workflow builds (`uv build`), runs `twine check`, and
   publishes via Trusted Publishing. Watch the Actions tab.
4. Verify:
   ```
   pip index versions devmemory-ai      # new version listed
   uvx --from devmemory-ai devmemory --help
   ```

## Local dry run (optional)

```
uv build                 # -> dist/devmemory_ai-<ver>-py3-none-any.whl + .tar.gz
uvx twine check dist/*   # metadata sanity
```

## Notes

- **First release is `0.1.0`.** Bump for every publish — PyPI refuses to overwrite
  an existing version.
- The wheel bundles the REST server too (FastAPI/SQLAlchemy). A pure MCP client
  doesn't need those; slimming the client into a separate install (core deps +
  a `[server]` extra) is a worthwhile future optimization but not required to ship.
