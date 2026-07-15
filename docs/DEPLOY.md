# Deploying DevMemory (hosted SaaS)

DevMemory has two parts that deploy to opposite places:

| Part | Runs where | How it ships |
|------|-----------|--------------|
| **Backend** (REST API + dashboard + DB) | Your server | You host it (this guide) |
| **Client** (MCP server + `devmemory` CLI) | Each user's laptop | They install it (see step 4) |

The client never connects to the database — it calls the backend over HTTPS with
an API key. So "deploy" means: **host the backend + give it a Postgres database.**

Recommended free stack: **Neon** (Postgres) + **Render** (Docker web service). $0.

---

## Prerequisites

- This repo pushed to GitHub (Render deploys from a Git repo).
- A [Neon](https://neon.tech) account and a [Render](https://render.com) account.

---

## Step 1 — Create the database (Neon)

1. Neon console → **Create project** (pick a region near your users).
2. Open **Connection Details** → copy the connection string. **Paste it verbatim** —
   no editing needed:
   ```
   postgresql://USER:PASSWORD@ep-xxx.REGION.aws.neon.tech/neondb?sslmode=require
   ```
   > DevMemory rewrites `postgresql://` → `postgresql+asyncpg://` and
   > `sslmode=require` → asyncpg's `ssl=require` automatically at startup, so the
   > raw Neon string works as-is.
   >
   > Prefer the **Direct connection** string (not the `-pooler` one). asyncpg's
   > prepared statements don't play well with Neon's pgbouncer pooler; if you must
   > use the pooled host and hit `prepared statement ... already exists`, append
   > `&prepared_statement_cache_size=0`.

Keep this string for Step 2.

---

## Step 2 — Deploy the backend (Render)

The repo ships a [`render.yaml`](../render.yaml) Blueprint, so this is mostly clicks.

1. Render dashboard → **New → Blueprint** → connect this GitHub repo.
2. Render reads `render.yaml` and proposes a `devmemory` web service (Docker, free plan).
3. Set the one secret it can't know: **`DEVMEMORY_DATABASE_URL`** = the
   `postgresql+asyncpg://…` string from Step 1. (`DEVMEMORY_SECRET_KEY` is
   generated for you; `DEVMEMORY_DEPLOYMENT_MODE=saas` is preset.)
4. **Apply / Create**. On boot the container runs `alembic upgrade head`
   (creating the schema in your empty Neon DB) and then serves the API.

When the deploy is green, verify:
```
curl https://<your-app>.onrender.com/health      # {"status":"ok",...,"deployment_mode":"saas"}
open  https://<your-app>.onrender.com/docs        # interactive API docs
open  https://<your-app>.onrender.com/            # dashboard
```

> **Free-tier note:** the service spins down after ~15 min idle; the first
> request then takes ~30 s (cold start). Fine for personal use. For always-on,
> bump the Render plan or move the same image to Cloud Run / Fly.io — no code
> change, just repoint `DEVMEMORY_DATABASE_URL`.

---

## Step 3 — First account + API key

On the deployed dashboard: **sign up**, then create an **API key** (Keys view).
Copy the `dm_key_…` — it's shown once.

---

## Step 4 — Point tools at your backend

On each machine, install the client and aim it at your hosted API. There are two
clients — same features, pick whichever runtime you have:

**Python** — PyPI package `devmemory-ai` (provides the `devmemory` command):
```
uvx --from devmemory-ai devmemory install --all --api-key dm_key_… --host https://<your-app>.onrender.com
# or:  pipx install devmemory-ai && devmemory install --all --api-key dm_key_… --host …
```

**Node** — npm package `@commanderzero/devmemory`, no Python needed:
```
npx -y @commanderzero/devmemory@latest install --all --api-key dm_key_… --host https://<your-app>.onrender.com
```

> `@latest` forces a fresh fetch past any stale `npx` cache. For a permanent
> `devmemory` command (so `devmemory start`/`stop` work with no prefix), install
> once: `npm install -g @commanderzero/devmemory` (Node) or `pipx install devmemory-ai` (Python).
> If a global install then still gives `command not found`, npm's global bin dir
> isn't on PATH — on Linux use a sudo-free user prefix: `npm config set prefix ~/.local`
> and re-run (`~/.local/bin` is usually already on PATH).

Restart the AI tool. The MCP client now saves/reads context through your backend.

---

## Environment variables

| Var | Required | Notes |
|-----|----------|-------|
| `DEVMEMORY_DATABASE_URL` | ✅ | Neon `postgresql+asyncpg://…?sslmode=require` |
| `DEVMEMORY_SECRET_KEY` | ✅ | JWT signing key. Render generates one; rotate to invalidate all sessions. |
| `DEVMEMORY_DEPLOYMENT_MODE` | ✅ | `saas` (auth + quotas enforced) |
| `DEVMEMORY_LOG_LEVEL` | – | `INFO` (default) |
| `PORT` | – | Injected by Render/Cloud Run; the entrypoint honours it. |

---

## Migrations

Schema changes are Alembic migrations in [`alembic/versions/`](../alembic/versions).
The container runs `alembic upgrade head` on every boot (idempotent), so a normal
Render deploy applies pending migrations automatically. To create a new one after
changing models:
```
alembic revision --autogenerate -m "describe change"
```

## Self-hosting instead

Not hosting for others? `docker compose up` runs the same image against a local
SQLite volume (`docker-compose.yml`), and `devmemory install --all` (no `--host`)
points tools at `http://localhost:8765`.
