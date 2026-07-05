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
  devmemory inject [--cwd <dir>] [--tool <name>] [--host <url>] [--api-key <key>]

Env:
  DEVMEMORY_HOST      Backend URL (default http://localhost:8765)
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
