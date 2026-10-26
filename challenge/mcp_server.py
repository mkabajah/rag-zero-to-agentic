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
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

with contextlib.redirect_stdout(sys.stderr):        # stdout is reserved for the MCP protocol
    import agent_tools as T

_build = threading.Lock()


def ready():
    """Build your pipeline once (index, graph). The first caller builds; the others wait."""
    with _build, contextlib.redirect_stdout(sys.stderr):
        T._ready()


@contextlib.asynccontextmanager
async def warm_up(server):
    # Build in the background so the server answers the client's handshake at once:
    # Claude Code gives a server 30 s to start, and a big pipeline can take longer.
    threading.Thread(target=ready, daemon=True).start()
    yield


mcp = FastMCP("cv-agent", instructions=T.SYSTEM_PROMPT, lifespan=warm_up)


def quiet(fn):
    """Wait for the build, then run the tool with print() going to stderr (a print in
    pipeline.py must not reach stdout, or it breaks the MCP messages)."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        ready()
        with contextlib.redirect_stdout(sys.stderr):
            return fn(*args, **kwargs)
    return run


for fn in T.TOOLS:
    mcp.tool()(quiet(fn))

if __name__ == "__main__":
    mcp.run()
