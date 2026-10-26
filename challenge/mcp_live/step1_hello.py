"""
MCP LIVE · STEP 1 · the smallest MCP server: one tool, no RAG yet.

    npx @modelcontextprotocol/inspector .venv/bin/python challenge/mcp_live/step1_hello.py
    python challenge/mcp_live/client.py challenge/mcp_live/step1_hello.py list_cvs

What to notice:
  - a tool is a normal Python function; the decorator publishes it
  - the docstring and the type hints become what the model reads (name, description, schema)
  - mcp.run() talks JSON-RPC over stdin/stdout: the CLIENT starts this file, you never "open" it
"""
import os
import pathlib

from mcp.server.fastmcp import FastMCP

CV_DIR = pathlib.Path(os.getenv("CV_DIR", pathlib.Path(__file__).resolve().parents[1] / "cvs"))

mcp = FastMCP("cv-hello")


@mcp.tool()
def list_cvs() -> list[str]:
    """List the file names of all candidate CVs. Use it to see who applied."""
    return sorted(p.name for p in CV_DIR.iterdir() if p.suffix.lower() in (".pdf", ".docx"))


if __name__ == "__main__":
    mcp.run()          # stdio transport: never print() to stdout in an MCP server
