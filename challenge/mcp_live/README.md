# Build an MCP server live · from zero to Claude Code using your RAG

Three small servers, each one a step you can write in front of the class, plus a tiny client
that shows what Claude Code sends behind the scenes.

| File | What it adds | Lines |
|---|---|---|
| `step1_hello.py` | one tool, no RAG: `list_cvs()` | ~20 |
| `step2_search.py` | your **local vector DB** (Chroma on disk) as a tool: `search_cvs(question, k)` | ~40 |
| `step3_full.py` | more tools (`find_candidates`, `get_cv`), a **resource** (`jobs://…`) and a **prompt** (`shortlist`) | ~90 |
| `client.py` | a 50-line MCP client: initialize → tools/list → tools/call | |
| `check.py` | the pre-flight check: run it before class | |

The full server the students use is `challenge/mcp_server.py` (built on `agent_tools.py`).

## FastMCP: what we build with

`from mcp.server.fastmcp import FastMCP` is the high-level server inside the **official MCP Python SDK 1.x**
(`pip install "mcp[cli]<2"`). It started as the open-source FastMCP 1.0 project and was merged into the SDK.
It turns a decorated Python function into an MCP tool: the name, the docstring (description) and the type
hints (JSON schema), and it speaks JSON-RPC for you over stdio or HTTP.

| You write | FastMCP publishes |
|---|---|
| `@mcp.tool()` | `tools/list` + `tools/call` |
| `@mcp.resource("jobs://backend-engineer")` | `resources/list` + `resources/read` |
| `@mcp.prompt()` | `prompts/list` + `prompts/get` |
| `mcp.run()` / `mcp.run(transport="streamable-http")` | a local stdio server / an HTTP server many people can share |

Two names to know: the standalone **`fastmcp`** package (v4) continues the same API with extras
(composition, proxies, middleware, auth) and moving to it is one import line: `from fastmcp import FastMCP`.
And **MCP SDK 2.x** renamed its built-in server to `MCPServer`, so `mcp.server.fastmcp` no longer exists
there. That is why the repo pins `mcp<2`.

## The local vector DB

The chatbot's Level 2 stores every chunk in **Chroma, on your disk**: `challenge/chroma_db/`
(collection `cvs`, one 384-number MiniLM vector per chunk, about 120 chunks and 2 MB for 24 CVs).
The MCP servers in steps 2 and 3 **open the same database**; they do not rebuild it. The question is
embedded with the same model (`helpers.embed`), or the vectors would not match.

```bash
ls challenge/chroma_db                      # chroma.sqlite3 + one folder per collection index
python challenge/mcp_live/check.py          # shows the chunk count and a test search
```

## Before class (10 minutes, on the demo laptop)

```bash
cd rag-zero-to-agentic && git pull && source .venv/bin/activate
pip install "mcp[cli]<2" chromadb                       # if check.py says they are missing (NOT mcp 2.x: see below)
cp ~/rag-run/cvs/* challenge/cvs/                       # the real CVs (never commit them)
cp ~/rag-run/instructor/reference_pipeline_all_steps.py challenge/pipeline.py   # a finished pipeline for the demo
python challenge/mcp_live/check.py --build              # builds the DB, starts all 4 servers
```

You want to see `ALL GOOD · ready for the live demo`. On our run: 118 chunks from 24 CVs, and
each server answers in 1–16 seconds (the first call loads MiniLM).

If you want to keep your own `pipeline.py`, save it first: `cp challenge/pipeline.py ~/my_pipeline.py`.
The starter `pipeline.py` works for steps 1–3 (they fall back to `checkpoints/level3.py`), but
not for `mcp_server.py`, which runs on the student's pipeline.

## The live demo (25 minutes)

### 1 · The smallest server (5 min)
Open `step1_hello.py` and write it with the class: `FastMCP("cv-hello")`, one function, one
decorator, `mcp.run()`. Then show it two ways:

```bash
python challenge/mcp_live/client.py challenge/mcp_live/step1_hello.py              # list the tools
python challenge/mcp_live/client.py challenge/mcp_live/step1_hello.py list_cvs     # call one
npx @modelcontextprotocol/inspector python challenge/mcp_live/step1_hello.py        # a web UI (needs Node)
```

Point out: the docstring became the description, the type hints became the input schema, and
nothing is printed to stdout (stdout is the protocol).

### 2 · Your vector DB as a tool (7 min)
`ls challenge/chroma_db`, then write `search_cvs` in `step2_search.py`: open the Chroma DB,
embed the question, `query(n_results=k)`, return file name + score + text.

```bash
python challenge/mcp_live/client.py challenge/mcp_live/step2_search.py search_cvs '{"question": "Who knows Kafka?"}'
```

Now connect it to Claude Code:

```bash
claude mcp add cv-search -- .venv/bin/python challenge/mcp_live/step2_search.py
claude mcp list                      # cv-search: ... ✓ Connected
claude                               # ask: "Search the CVs: who has worked with n8n?"
```

### 3 · Tools, resources, prompts (8 min)
Show `step3_full.py`. Register it and ask a question that needs several tools:

```bash
claude mcp add cv-live -- .venv/bin/python challenge/mcp_live/step3_full.py
claude
> Using only the cv-live tools: which candidates know both Kafka and Kubernetes?
  Check one of them with get_cv and quote the evidence.
```

What Claude Code did on our run (real, 24 CVs): `search_cvs` ×3 → noticed top-k is not a list →
`find_candidates("Kafka")` = 5, `find_candidates("Kubernetes")` = 9 → "all 5 Kafka CVs also have
Kubernetes" → `get_cv` on one of them → quoted the skills line and a project line. **Nobody told it
to switch tools: it read the descriptions.** That is the lesson of the day.

Also try `/` in Claude Code to see the `shortlist` prompt, and `@` to attach the `jobs://` resource.

### 4 · The full Hiring Agent (5 min)
The repo's `.mcp.json` already has `cv-agent` (`challenge/mcp_server.py`) and the `hiring-agent`
subagent. `claude` in the repo → approve `cv-agent` → `/agents` → hiring-agent →
"Shortlist 3 candidates for the backend-engineer job". Then hand over to the students.

Clean up afterwards: `claude mcp remove cv-search` and `claude mcp remove cv-live`.

### 5 · Skills (after the break, 10 min)
The repo has two skills: `.claude/skills/shortlist-candidates/` and `.claude/skills/screen-cv/`
(the same files in `.kiro/skills/`). Open one, read the description line aloud: that is the trigger.

```bash
claude                                    # in the repo, cv-agent approved
> Shortlist candidates for the backend-engineer job.
```

On our run Claude Code called the skill by itself, then `list_jobs`, `find_candidates` once per must-have,
`get_cv` for the 5 CVs with all four (it fixed a wrong argument name from the error message), and
answered with the table, who to interview first, and red flags. 16 tool calls, 38 seconds.

### 6 · The agentic chatbot (Level 5, 10 min)
For the demo, use the finished graph on top of the naive pipeline (what students will have):

```bash
cp challenge/checkpoints/level3.py challenge/pipeline.py          # or keep the reference
cp challenge/checkpoints/agentic_done.py challenge/agentic.py
python challenge/app.py                                           # Chat tab
```

Ask "Which candidates know Kafka?" twice: without and with **Agentic RAG** ticked. Naive: "I don't
know" (0 of 5). Agentic: route → LIST → find_all → all 5 CVs with the line that proves each one.
Then "…worked on the construction of a huge chip factory?" (grade WEAK → rewrite → found) and
"Which candidate has Salesforce experience?" (0 of 24 → refuse). Put the starter back afterwards:
`git checkout challenge/agentic.py challenge/pipeline.py`.

Measured with Verify (retrieval only, 24 real CVs): naive 6/10 practice and 5/15 hidden → agentic
9/10 and 8/15. On the full Level 4 pipeline: 9/10 and 11/15 → 10/10 and 13/15. The cost is time:
1–10 s per question instead of well under one second.

## The same server in other clients

**Kiro** (`.kiro/settings/mcp.json` in the workspace, or `~/.kiro/settings/mcp.json`):
```json
{"mcpServers": {"cv-live": {"command": ".venv/bin/python", "args": ["challenge/mcp_live/step3_full.py"]}}}
```

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`, absolute paths):
```json
{"mcpServers": {"cv-live": {"command": "/Users/you/rag-zero-to-agentic/.venv/bin/python",
                            "args": ["/Users/you/rag-zero-to-agentic/challenge/mcp_live/step3_full.py"]}}}
```

**Strands**: `python challenge/frameworks/strands_agent.py --mcp "…"` (see `../frameworks/README.md`).

## If something breaks

| Symptom | Cause | Fix |
|---|---|---|
| `✗ Failed to connect` in `claude mcp list` | wrong python (system python has no packages) | use `.venv/bin/python`, not `python` |
| `Collection [cvs] does not exist` | the DB was never built | `python challenge/mcp_live/check.py --build`, or open the chatbot once |
| The server hangs, or JSON errors in the client | something `print()`s to stdout | print to stderr, or wrap in `contextlib.redirect_stdout(sys.stderr)` |
| Very slow first call | MiniLM loads on the first embed | the servers warm up at start; wait ~10 s |
| Search results look random | the embedder fell back to TF-IDF (no model) | `check.py` step 3 must say `SentenceTransformerEmbedder, 384` |
| One CV never appears | a parsing trap (a DOCX with text in a table) | `check.py` names it; fix `load_cvs` |
| Old results after rebuilding the index | the collection handle was cached | the servers fetch the collection on every call |
| `ModuleNotFoundError: mcp.server.fastmcp` | MCP SDK 2.x is installed (it renamed the server to `MCPServer`) | `pip install "mcp[cli]<2"`, or switch to standalone FastMCP: `pip install fastmcp` and `from fastmcp import FastMCP` |
| `CONNECT_TIMEOUT` in Claude Code | the server took more than 30 s to start | build in the background (see `mcp_server.py`), or start Claude with `MCP_TIMEOUT=60000 claude` |
