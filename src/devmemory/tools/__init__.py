"""DevMemory MCP tools — a thin HTTP client over the DevMemory REST API.

The MCP server runs on the user's machine (each AI tool launches it). It does
**not** touch the database directly: it authenticates to the DevMemory REST API
with the user's API key and lets the server — which owns the database — perform
every read and write. This keeps database credentials off client machines and
lets one hosted backend serve every tool (Claude, Cursor, Windsurf, …).

Only project/git resolution happens client-side (in :func:`resolve_project_slug`),
because only the client can see the working directory. The resolved
``slug``/``name``/``remote_url`` is sent to the API as a ``ProjectRef``.

Configuration:
    DEVMEMORY_HOST      REST base URL (default ``http://localhost:8765``).
    DEVMEMORY_API_KEY   API key, used when a tool call omits ``api_key``.
"""

from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

from devmemory.auth.mcp_auth import _pick_key
from devmemory.models.context import BlockType
from devmemory.resolver.git_resolver import resolve_project_slug

# ── Configuration ───────────────────────────────────────────────────────────────

_DEFAULT_HOST = "http://localhost:8765"
# Generous timeout: managed free tiers (Render/Fly) cold-start ~30-50s when idle,
# so the first tool call after a lull must wait rather than fail.
_TIMEOUT = 60.0


def _host() -> str:
    return (os.environ.get("DEVMEMORY_HOST") or _DEFAULT_HOST).rstrip("/")


# ── FastMCP instance (imported by server.py) ───────────────────────────────────

mcp = FastMCP(
    name="devmemory",
    instructions=(
        "DevMemory is the user's persistent memory layer. It ensures their work context "
        "survives across AI tool switches (e.g. Claude → Cursor → Windsurf) and credit resets. "
        "Without saved context, the user loses everything when they switch tools. "
        "\n\n"
        "## Which project? Always pass `cwd`.\n"
        "Every project tool takes a `cwd` argument that selects the project. ALWAYS pass the "
        "absolute path of the project folder currently open in this tool — that folder IS the "
        "project (DevMemory resolves it by git remote or folder name; the user never names it). "
        "Only pass an explicit `project` if the user wants a different one than the open folder; "
        "use `list_projects` to see what exists.\n"
        "\n"
        "## FIRST, attach + restore: continue_here\n"
        "When the user says 'start', 'continue', 'resume', 'pick up where we left off', or at the "
        "start of any session on an existing project: call `continue_here(cwd=<open folder>)`. ONE "
        "call attaches auto-save to this project AND returns the prior context to read. Do this "
        "before get_context/generate_resume_prompt — nothing auto-saves until a project is attached.\n"
        "\n"
        "## CRITICAL: You MUST call save_context proactively. Do NOT wait to be asked.\n"
        "\n"
        "### When to call save_context (always with the same `cwd`):\n"
        "- SESSION START: Immediately call save_context with block_type='goal' "
        "describing what the user wants to accomplish.\n"
        "- AFTER EVERY FILE EDIT or code change: save block_type='code' with a "
        "summary of what was changed and why.\n"
        "- AFTER EVERY KEY DECISION: save block_type='decision' when an "
        "architectural, design, or implementation choice is made.\n"
        "- ON EVERY ERROR: save block_type='error' with the error message and "
        "what fix was attempted.\n"
        "- BEFORE ENDING: save block_type='next_step' with exactly what needs to be done next.\n"
        "- AT ANY NATURAL PAUSE: save block_type='note' with any context that "
        "would help someone picking this up fresh.\n"
        "\n"
        "### Task Tracking:\n"
        "- WHEN CREATING A TASK LIST: call save_tasks with all tasks at once. "
        "Store returned task_ids.\n"
        '- BEFORE STARTING each task: call update_task(block_id, "in_progress").\n'
        '- AFTER COMPLETING each task: call update_task(block_id, "done").\n'
        "\n"
        "### When to call continue_here:\n"
        "- When the user says 'continue', 'resume', 'pick up where we left off', or switches\n"
        "  into this tool and wants prior context. ONE call attaches auto-save to this project\n"
        "  AND returns the resume prompt. Prefer it over get_context/generate_resume_prompt for\n"
        "  restoring, because auto-save saves nothing until a project is attached.\n"
        "\n"
        "### When to call get_context or generate_resume_prompt:\n"
        "- At the start of a session to inspect prior work without attaching.\n"
        "\n"
        "### Authentication:\n"
        "Use the api_key argument or the DEVMEMORY_API_KEY environment variable.\n"
        "\n"
        "Saving context is not optional — it is core to why DevMemory exists. "
        "A session with no saved blocks is a session the user cannot recover from."
    ),
)


# ── Helpers ────────────────────────────────────────────────────────────────────

_VALID_BLOCK_TYPES = {bt.value for bt in BlockType}
_VALID_TASK_STATUSES = {"pending", "in_progress", "done", "skipped"}
_VALID_END_STATUSES = {"completed", "archived", "paused"}


def _err(msg: str) -> dict:
    """Standard error response dict."""
    return {"ok": False, "error": msg}


def _project_ref(proj) -> dict:
    """Build the ProjectRef payload from a resolved ProjectInfo."""
    return {"slug": proj.slug, "name": proj.name, "remote_url": proj.remote_url}


async def _api(
    method: str,
    path: str,
    api_key: str | None,
    *,
    json: dict | None = None,
    params: dict | None = None,
) -> dict:
    """Call the DevMemory REST API with the user's API key.

    Returns the parsed JSON body on success, or an ``{"ok": False, "error": ...}``
    dict on any failure (missing key, network error, or 4xx/5xx response) so tool
    handlers can return it verbatim.
    """
    try:
        key = _pick_key(api_key)
    except ValueError as exc:
        return _err(str(exc))

    url = f"{_host()}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.request(
                method, url, headers={"X-API-Key": key}, json=json, params=params
            )
    except httpx.RequestError as exc:
        return _err(
            f"Could not reach DevMemory at {_host()} ({exc}). "
            "Set DEVMEMORY_HOST, or start the server with `devmemory --rest`."
        )

    if resp.status_code >= 400:
        detail = None
        try:
            detail = resp.json().get("detail")
        except Exception:
            detail = None
        return _err(detail or f"HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        return resp.json()
    except Exception:
        return _err("Invalid (non-JSON) response from the DevMemory server")


# ── Tool: save_context ─────────────────────────────────────────────────────────


@mcp.tool()
async def save_context(
    block_type: str,
    content: str,
    cwd: str,
    session_id: str | None = None,
    project: str | None = None,
    priority: int = 5,
    api_key: str | None = None,
) -> dict:
    """Save a typed context block to the active session.

    If no ``session_id`` is supplied the server reuses the most recent active
    session for the project, or creates one automatically.

    Args:
        block_type: One of: goal, decision, code, error, next_step, note, task.
        content:    The context content to save.
        cwd:        Working directory — resolved locally to a project (git remote).
        session_id: Optional existing session ID to append to.
        project:    Optional explicit project name (overrides git detection).
        priority:   Ordering weight for resume prompts (1–10, default 5).
        api_key:    DevMemory API key. Falls back to DEVMEMORY_API_KEY env var.
    """
    norm = block_type.lower().strip()
    if norm not in _VALID_BLOCK_TYPES:
        valid = ", ".join(sorted(_VALID_BLOCK_TYPES))
        return _err(f"Invalid block_type '{block_type}'. Must be one of: {valid}")
    if not content.strip():
        return _err("content must not be empty")
    if not 1 <= priority <= 10:
        return _err("priority must be between 1 and 10")

    proj = await resolve_project_slug(cwd, explicit_project=project)
    payload: dict = {
        "project": _project_ref(proj),
        "block_type": norm,
        "content": content.strip(),
        "priority": priority,
    }
    if session_id:
        payload["session_id"] = session_id
    return await _api("POST", "/context", api_key, json=payload)


# ── Tool: save_tasks ───────────────────────────────────────────────────────────


@mcp.tool()
async def save_tasks(
    tasks: list[dict],
    cwd: str,
    session_id: str | None = None,
    project: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Save a list of tasks as individual 'task' context blocks.

    Each task dict can contain: ``title`` (str), ``description`` (str, optional),
    ``priority`` (int, optional).

    Args:
        tasks:      List of task dictionaries.
        cwd:        Working directory — resolved locally to a project.
        session_id: Optional existing session ID to append to.
        project:    Optional explicit project name.
        api_key:    DevMemory API key.
    """
    if not tasks:
        return _err("tasks list must not be empty")

    proj = await resolve_project_slug(cwd, explicit_project=project)
    payload: dict = {
        "project": _project_ref(proj),
        "tasks": [
            {
                "title": t.get("title") or f"Task {i + 1}",
                "description": t.get("description"),
                "priority": t.get("priority", 5),
            }
            for i, t in enumerate(tasks)
        ],
    }
    if session_id:
        payload["session_id"] = session_id
    return await _api("POST", "/context/tasks", api_key, json=payload)


# ── Tool: update_task ──────────────────────────────────────────────────────────


@mcp.tool()
async def update_task(
    block_id: str,
    status: str,
    cwd: str,
    session_id: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Update a task's status (pending, in_progress, done, skipped).

    Args:
        block_id:   The task block ID returned from save_tasks.
        status:     The new status.
        cwd:        Working directory (unused; kept for tool-call compatibility).
        session_id: Optional session ID (unused; kept for compatibility).
        api_key:    DevMemory API key.
    """
    if status not in _VALID_TASK_STATUSES:
        return _err(f"status must be one of: {', '.join(sorted(_VALID_TASK_STATUSES))}")
    return await _api(
        "PATCH", f"/context/blocks/{block_id}/status", api_key, json={"status": status}
    )


# ── Tool: get_context ──────────────────────────────────────────────────────────


@mcp.tool()
async def get_context(
    cwd: str,
    session_id: str | None = None,
    block_type: str | None = None,
    limit: int = 50,
    api_key: str | None = None,
) -> dict:
    """Retrieve context blocks for the current project / session.

    Args:
        cwd:        Working directory — resolved locally to a project if no
                    ``session_id`` is given.
        session_id: Specific session to query. If omitted, the latest active
                    session for the project is used.
        block_type: Optional filter — return only blocks of this type.
        limit:      Maximum number of blocks to return (default 50).
        api_key:    DevMemory API key.
    """
    params: dict = {"limit": limit}
    if block_type is not None:
        norm = block_type.lower().strip()
        if norm not in _VALID_BLOCK_TYPES:
            valid = ", ".join(sorted(_VALID_BLOCK_TYPES))
            return _err(f"Invalid block_type '{block_type}'. Must be one of: {valid}")
        params["block_type"] = norm

    if session_id:
        params["session_id"] = session_id
    else:
        proj = await resolve_project_slug(cwd)
        params["project_slug"] = proj.slug

    return await _api("GET", "/context", api_key, params=params)


# ── Tool: start_session ────────────────────────────────────────────────────────


@mcp.tool()
async def start_session(
    title: str,
    cwd: str,
    tool_source: str = "unknown",
    project: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Begin a new development session.

    Args:
        title:       Human-readable session title, e.g. "Implement auth layer".
        cwd:         Working directory — resolved locally to a project.
        tool_source: The AI tool starting this session (e.g. "claude", "cursor").
        project:     Optional explicit project name override.
        api_key:     DevMemory API key.
    """
    if not title.strip():
        return _err("title must not be empty")

    proj = await resolve_project_slug(cwd, explicit_project=project)
    payload = {
        "project": _project_ref(proj),
        "title": title.strip(),
        "tool_source": tool_source,
    }
    return await _api("POST", "/sessions", api_key, json=payload)


# ── Tool: end_session ──────────────────────────────────────────────────────────


@mcp.tool()
async def end_session(
    session_id: str,
    status: str = "completed",
    api_key: str | None = None,
) -> dict:
    """Mark a session as completed or archived.

    Args:
        session_id: The session ID returned by ``start_session``.
        status:     One of: completed, archived, paused (default: completed).
        api_key:    DevMemory API key.
    """
    if status not in _VALID_END_STATUSES:
        return _err(f"status must be one of: {', '.join(sorted(_VALID_END_STATUSES))}")

    result = await _api("PATCH", f"/sessions/{session_id}", api_key, json={"status": status})
    if result.get("ok") is False:
        return result
    return {
        "ok": True,
        "session_id": result.get("id", session_id),
        "status": result.get("status", status),
    }


# ── Tool: list_sessions ────────────────────────────────────────────────────────


@mcp.tool()
async def list_sessions_tool(
    cwd: str,
    project: str | None = None,
    status: str | None = None,
    limit: int = 10,
    api_key: str | None = None,
) -> dict:
    """List recent development sessions for the current project.

    Args:
        cwd:     Working directory — resolved locally to a project.
        project: Optional explicit project name override.
        status:  Optional filter: active, paused, completed, archived.
        limit:   Maximum sessions to return (default 10).
        api_key: DevMemory API key.
    """
    proj = await resolve_project_slug(cwd, explicit_project=project)
    params: dict = {"project_slug": proj.slug, "limit": limit}
    if status:
        params["status"] = status

    result = await _api("GET", "/sessions", api_key, params=params)
    if result.get("ok") is False:
        return result
    return {
        "ok": True,
        "project_slug": proj.slug,
        "sessions": result.get("sessions", []),
        "count": result.get("count", 0),
    }


# ── Tool: generate_resume_prompt ───────────────────────────────────────────────


@mcp.tool()
async def generate_resume_prompt(
    session_id: str,
    target_tool: str = "generic",
    api_key: str | None = None,
) -> dict:
    """Generate an optimised "continue here" prompt for switching AI tools.

    Args:
        session_id:  The session to generate a prompt for.
        target_tool: Tailors the preamble: claude, cursor, windsurf, or generic.
        api_key:     DevMemory API key.
    """
    return await _api(
        "GET", f"/sessions/{session_id}/resume", api_key, params={"target_tool": target_tool}
    )


# ── Tool: continue_here ──────────────────────────────────────────────────────────


@mcp.tool()
async def continue_here(
    cwd: str,
    tool_source: str = "unknown",
    api_key: str | None = None,
) -> dict:
    """Attach DevMemory auto-save to THIS project and load its saved context.

    Call this when the user switches into this tool and says "continue", "resume",
    "pick up where we left off", or otherwise wants their prior context here.

    Two things happen:
    1. **Attach** — the current project becomes the active session, so background
       auto-save (watch daemon + deterministic hooks) is scoped to it. Auto-save
       is strictly opt-in: it saves nothing until a project is attached this way
       or via ``devmemory start``.
    2. **Restore** — the latest session's context is returned as a ``prompt`` you
       should read to continue seamlessly.

    Args:
        cwd:         Working directory — resolved locally to a project.
        tool_source: The AI tool being attached (e.g. "claude", "cursor").
        api_key:     DevMemory API key. Falls back to DEVMEMORY_API_KEY env var.
    """
    proj = await resolve_project_slug(cwd)

    # Attach: write the local marker so background auto-save scopes to this
    # project. Best-effort — a failure here must not block the restore.
    attached = False
    try:
        from devmemory.hooks._common import write_active

        write_active(
            {"slug": proj.slug, "name": proj.name, "remote_url": proj.remote_url}, tool_source
        )
        attached = True
    except Exception:  # noqa: BLE001 — marker is best-effort
        attached = False

    # On-demand sync: scan local tool stores for THIS project and push any new
    # turns to the backend — no persistent daemon required. Fire-and-forget in a
    # background daemon thread so a large first-run backlog can't stall the
    # restore; the watermark advances per fully-saved conversation, so a partial
    # run resumes cleanly on the next call. This is what makes capture work
    # without the watch daemon: every tool calls continue_here at session start.
    try:
        import threading

        from devmemory.watch.sync import sync_now

        threading.Thread(
            target=sync_now, args=(proj.slug, _pick_key(api_key)), daemon=True
        ).start()
    except Exception:  # noqa: BLE001 — sync is strictly best-effort
        pass

    sess = await _api(
        "GET",
        "/sessions",
        api_key,
        params={"project_slug": proj.slug, "status": "active", "limit": 1},
    )
    if sess.get("ok") is False:
        return sess
    sessions = sess.get("sessions", [])
    if not sessions:
        return {
            "ok": True,
            "attached": attached,
            "project": proj.name,
            "has_context": False,
            "message": (
                f"Attached to '{proj.name}' — auto-save is now scoped to this project. "
                "No prior session to restore; starting fresh."
            ),
        }

    session_id = sessions[0].get("id")
    resume = await _api(
        "GET", f"/sessions/{session_id}/resume", api_key, params={"target_tool": tool_source}
    )
    if resume.get("ok") is False:
        return resume
    return {
        "ok": True,
        "attached": attached,
        "project": proj.name,
        "session_id": session_id,
        "has_context": resume.get("has_context", True),
        "prompt": resume.get("prompt"),
        "message": (
            f"Attached to '{proj.name}' and loaded prior context. "
            "Read the prompt below to continue where you left off."
        ),
    }


# ── Tool: list_projects ────────────────────────────────────────────────────────


@mcp.tool()
async def list_projects_tool(api_key: str | None = None) -> dict:
    """List all projects known to DevMemory for this account.

    Args:
        api_key: DevMemory API key.
    """
    result = await _api("GET", "/projects", api_key)
    if result.get("ok") is False:
        return result
    return {
        "ok": True,
        "projects": result.get("projects", []),
        "count": result.get("count", 0),
    }
