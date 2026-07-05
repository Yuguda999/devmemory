// DevMemory MCP stdio server (Node). Exposes the same tools as the Python
// client; each is a thin wrapper over the REST API. Tool names match the Python
// client so agents see an identical surface regardless of which client runs.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { apiCall } from "./api.js";
import { resolveProject } from "./git.js";

const INSTRUCTIONS = [
  "DevMemory is the user's persistent memory layer. It ensures their work context",
  "survives across AI tool switches (e.g. Claude → Cursor → Windsurf) and credit resets.",
  "",
  "## CRITICAL: You MUST call save_context proactively. Do NOT wait to be asked.",
  "- SESSION START: save_context block_type='goal' describing the objective.",
  "- AFTER EVERY FILE EDIT / code change: save_context block_type='code'.",
  "- AFTER EVERY KEY DECISION: save_context block_type='decision'.",
  "- ON EVERY ERROR: save_context block_type='error'.",
  "- BEFORE ENDING: save_context block_type='next_step'.",
  "",
  "Task tracking: save_tasks to create, update_task to advance status.",
  "On resume ('continue', 'pick up where we left off'): call get_context or generate_resume_prompt.",
  "Authenticate via the api_key argument or the DEVMEMORY_API_KEY environment variable.",
].join("\n");

const result = (obj) => ({ content: [{ type: "text", text: JSON.stringify(obj) }] });

export function buildServer() {
  const server = new McpServer(
    { name: "devmemory", version: "0.1.0" },
    { instructions: INSTRUCTIONS },
  );

  server.tool(
    "save_context",
    "Save a typed context block to the active session (auto-creates the session).",
    {
      block_type: z.string().describe("goal, decision, code, error, next_step, note, task"),
      content: z.string(),
      cwd: z.string().describe("Working directory — resolved locally to a project"),
      session_id: z.string().optional(),
      project: z.string().optional(),
      priority: z.number().int().min(1).max(10).optional(),
      api_key: z.string().optional(),
    },
    async (a) => {
      const json = {
        project: resolveProject(a.cwd, a.project),
        block_type: a.block_type,
        content: a.content,
        priority: a.priority ?? 5,
      };
      if (a.session_id) json.session_id = a.session_id;
      return result(await apiCall("POST", "/context", { apiKey: a.api_key, json }));
    },
  );

  server.tool(
    "save_tasks",
    "Save a list of tasks as individual 'task' context blocks.",
    {
      tasks: z.array(z.object({
        title: z.string(),
        description: z.string().optional(),
        priority: z.number().int().optional(),
      })),
      cwd: z.string(),
      session_id: z.string().optional(),
      project: z.string().optional(),
      api_key: z.string().optional(),
    },
    async (a) => {
      const json = { project: resolveProject(a.cwd, a.project), tasks: a.tasks };
      if (a.session_id) json.session_id = a.session_id;
      return result(await apiCall("POST", "/context/tasks", { apiKey: a.api_key, json }));
    },
  );

  server.tool(
    "update_task",
    "Update a task block's status (pending, in_progress, done, skipped).",
    {
      block_id: z.string(),
      status: z.string(),
      cwd: z.string().optional(),
      session_id: z.string().optional(),
      api_key: z.string().optional(),
    },
    async (a) =>
      result(await apiCall(
        "PATCH",
        `/context/blocks/${encodeURIComponent(a.block_id)}/status`,
        { apiKey: a.api_key, json: { status: a.status } },
      )),
  );

  server.tool(
    "get_context",
    "Retrieve context blocks for the current project or an explicit session.",
    {
      cwd: z.string(),
      session_id: z.string().optional(),
      block_type: z.string().optional(),
      limit: z.number().int().optional(),
      api_key: z.string().optional(),
    },
    async (a) => {
      const params = { limit: a.limit ?? 50 };
      if (a.block_type) params.block_type = a.block_type;
      if (a.session_id) params.session_id = a.session_id;
      else params.project_slug = resolveProject(a.cwd).slug;
      return result(await apiCall("GET", "/context", { apiKey: a.api_key, params }));
    },
  );

  server.tool(
    "start_session",
    "Begin a new development session for the current project.",
    {
      title: z.string(),
      cwd: z.string(),
      tool_source: z.string().optional(),
      project: z.string().optional(),
      api_key: z.string().optional(),
    },
    async (a) =>
      result(await apiCall("POST", "/sessions", {
        apiKey: a.api_key,
        json: {
          project: resolveProject(a.cwd, a.project),
          title: a.title,
          tool_source: a.tool_source ?? "unknown",
        },
      })),
  );

  server.tool(
    "end_session",
    "Mark a session completed, archived, or paused.",
    {
      session_id: z.string(),
      status: z.string().optional(),
      api_key: z.string().optional(),
    },
    async (a) => {
      const status = a.status ?? "completed";
      const r = await apiCall(
        "PATCH",
        `/sessions/${encodeURIComponent(a.session_id)}`,
        { apiKey: a.api_key, json: { status } },
      );
      if (r.ok === false) return result(r);
      return result({ ok: true, session_id: r.id ?? a.session_id, status: r.status ?? status });
    },
  );

  server.tool(
    "list_sessions_tool",
    "List recent development sessions for the current project.",
    {
      cwd: z.string(),
      project: z.string().optional(),
      status: z.string().optional(),
      limit: z.number().int().optional(),
      api_key: z.string().optional(),
    },
    async (a) => {
      const slug = resolveProject(a.cwd, a.project).slug;
      const params = { project_slug: slug, limit: a.limit ?? 10 };
      if (a.status) params.status = a.status;
      const r = await apiCall("GET", "/sessions", { apiKey: a.api_key, params });
      if (r.ok === false) return result(r);
      return result({ ok: true, project_slug: slug, sessions: r.sessions ?? [], count: r.count ?? 0 });
    },
  );

  server.tool(
    "generate_resume_prompt",
    "Generate an optimised 'continue here' prompt for a session.",
    {
      session_id: z.string(),
      target_tool: z.string().optional(),
      api_key: z.string().optional(),
    },
    async (a) =>
      result(await apiCall(
        "GET",
        `/sessions/${encodeURIComponent(a.session_id)}/resume`,
        { apiKey: a.api_key, params: { target_tool: a.target_tool ?? "generic" } },
      )),
  );

  server.tool(
    "list_projects_tool",
    "List all projects known to DevMemory for this account.",
    {
      api_key: z.string().optional(),
    },
    async (a) => {
      const r = await apiCall("GET", "/projects", { apiKey: a.api_key });
      if (r.ok === false) return result(r);
      return result({ ok: true, projects: r.projects ?? [], count: r.count ?? 0 });
    },
  );

  return server;
}

export async function runMcp() {
  const server = buildServer();
  await server.connect(new StdioServerTransport());
}
