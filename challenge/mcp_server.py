"""
YOUR RAG AS AN MCP SERVER · use your pipeline from Claude Code, Claude Desktop or Kiro.

    python challenge/mcp_server.py        (it waits silently for a client; Ctrl+C to stop)

Claude Code:  the repo's .mcp.json defines "cv-agent": start `claude` in the repo and approve it.
Kiro:         .kiro/settings/mcp.json defines "cv-agent": open the repo as the workspace.
Then ask:     "Use list_jobs, then shortlist the 3 best candidates for the backend job, with
               evidence from each CV and one risk each."

The tools are the four functions in challenge/agent_tools.py, built on YOUR pipeline.py.
"""
import contextlib
import functools
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

with contextlib.redirect_stdout(sys.stderr):        # stdout is reserved for the MCP protocol
    import agent_tools as T
    T._ready()

mcp = FastMCP("cv-agent", instructions=T.SYSTEM_PROMPT)


def quiet(fn):
    """Run a tool with print() going to stderr, so a print in pipeline.py cannot break MCP."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        with contextlib.redirect_stdout(sys.stderr):
            return fn(*args, **kwargs)
    return run


for fn in T.TOOLS:
    mcp.tool()(quiet(fn))

if __name__ == "__main__":
    mcp.run()
