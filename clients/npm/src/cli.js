#!/usr/bin/env node
// DevMemory CLI entry point.
//
//   devmemory                 — start the MCP stdio server (default; for AI tools)
//   devmemory mcp             — same, explicit
//   devmemory install --tool cursor --api-key dm_key_... --host https://...
//   devmemory install --all   --api-key dm_key_... --host https://...
//   devmemory inject [--cwd .] [--tool claude] [--host ...] [--api-key ...]

import { parseArgs } from "node:util";

const args = process.argv.slice(2);
let cmd = "mcp";
let rest = args;
if (args[0] && !args[0].startsWith("-")) {
  cmd = args[0];
  rest = args.slice(1);
} else if (args[0] === "--help" || args[0] === "-h") {
  cmd = "help";
}

function printHelp() {
  console.log(`DevMemory — persistent cross-tool coding memory

Usage:
  devmemory                                   Start the MCP server (stdio)
  devmemory mcp                               Start the MCP server (explicit)
  devmemory install --tool <name>|--all --api-key <key> [--host <url>]
  devmemory start    [--cwd <dir>] [--tool <name>] [--host <url>] [--api-key <key>]
  devmemory continue [--cwd <dir>] [--tool <name>] [--host <url>] [--api-key <key>]
  devmemory stop
  devmemory status
  devmemory inject   [--cwd <dir>] [--tool <name>] [--host <url>] [--api-key <key>]

Attach model:
  start      Attach the current project, restore its context, begin saving.
  continue   Re-attach the active project in a new tool and restore context.
  stop       Detach (stop auto-saving).
  status     Show the active session.
  Note: the background watch daemon (store-based tools) is Python-only.

Env:
  DEVMEMORY_HOST      Backend URL (also read from ~/.devmemory/config.json)
  DEVMEMORY_API_KEY   API key (fallback when --api-key is omitted)`);
}

async function main() {
  if (cmd === "mcp") {
    const { runMcp } = await import("./mcp.js");
    await runMcp();
    return;
  }

  if (cmd === "install") {
    const { runInstall, TOOL_SLUGS } = await import("./install.js");
    const { values } = parseArgs({
      args: rest,
      options: {
        tool: { type: "string" },
        "api-key": { type: "string" },
        host: { type: "string" },
        all: { type: "boolean" },
      },
      allowPositionals: false,
    });
    const tool = values.all ? "all" : values.tool;
    if (!tool) {
      console.error(`❌ Specify --tool <${TOOL_SLUGS.join("|")}> or --all`);
      process.exit(1);
    }
    runInstall({ tool, apiKey: values["api-key"], host: values.host });
    return;
  }

  if (cmd === "start" || cmd === "continue") {
    const session = await import("./session.js");
    const { values } = parseArgs({
      args: rest,
      options: {
        cwd: { type: "string" },
        tool: { type: "string" },
        host: { type: "string" },
        "api-key": { type: "string" },
      },
      allowPositionals: false,
    });
    const opts = {
      cwd: values.cwd,
      tool: values.tool,
      host: values.host,
      apiKey: values["api-key"],
    };
    await (cmd === "start" ? session.runStart(opts) : session.runContinue(opts));
    return;
  }

  if (cmd === "stop") {
    const { runStop } = await import("./session.js");
    runStop();
    return;
  }

  if (cmd === "status") {
    const { runStatus } = await import("./session.js");
    runStatus();
    return;
  }

  if (cmd === "inject") {
    const { runInject } = await import("./inject.js");
    const { values } = parseArgs({
      args: rest,
      options: {
        cwd: { type: "string" },
        tool: { type: "string" },
        host: { type: "string" },
        "api-key": { type: "string" },
      },
      allowPositionals: false,
    });
    if (values.host) process.env.DEVMEMORY_HOST = values.host;
    await runInject({ cwd: values.cwd, tool: values.tool, apiKey: values["api-key"] });
    return;
  }

  if (cmd === "help") {
    printHelp();
    return;
  }

  console.error(`Unknown command: ${cmd}\n`);
  printHelp();
  process.exit(1);
}

main().catch((e) => {
  console.error(e?.stack || String(e));
  process.exit(1);
});
