"""
A tiny MCP client: what Claude Code / Kiro do behind the scenes.

    python challenge/mcp_live/client.py <server.py>                          list the tools
    python challenge/mcp_live/client.py <server.py> <tool> '<json args>'      call one tool

It starts the server as a subprocess, says hello (initialize), asks for the tools (tools/list)
and calls one (tools/call): three JSON-RPC messages over stdin/stdout.
"""
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(server, tool=None, args="{}"):
    params = StdioServerParameters(command=sys.executable, args=[server], env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            print(f"connected to '{info.serverInfo.name}'\n")
            if not tool:
                for t in (await session.list_tools()).tools:
                    props = ", ".join(f"{k}: {v.get('type', '?')}" for k, v in t.inputSchema.get("properties", {}).items())
                    print(f"TOOL  {t.name}({props})\n      {t.description.strip().splitlines()[0]}")
                with_extra = [("RESOURCE", session.list_resources, "resources", "uri"),
                              ("RESOURCE", session.list_resource_templates, "resourceTemplates", "uriTemplate"),
                              ("PROMPT", session.list_prompts, "prompts", "name")]
                for kind, call, field, key in with_extra:
                    try:
                        for x in getattr(await call(), field):
                            print(f"{kind:8s}  {getattr(x, key)}")
                    except Exception:
                        pass
                return
            result = await session.call_tool(tool, json.loads(args))
            for part in result.content:
                text = getattr(part, "text", str(part))
                try:
                    print(json.dumps(json.loads(text), indent=2, ensure_ascii=False))
                except ValueError:
                    print(text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(*sys.argv[1:4]))
