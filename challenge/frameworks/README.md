# The same RAG, four agent frameworks

All four files use the **same tools** from `challenge/agent_tools.py` (built on YOUR `pipeline.py`):
`search_cvs`, `get_cv`, `find_candidates`, `list_jobs`. Only the framework around them changes.

| File | Framework | Idea | Model | Install |
|---|---|---|---|---|
| `langgraph_agentic_rag.py` | LangGraph | you draw the loop as a graph: retrieve → grade → rewrite → generate | the local model from `helpers.llm` (no key) | `pip install langgraph` |
| `langchain_agent.py` | LangChain 1.x | `create_agent(model, tools)`: a ready-made ReAct loop | `LC_MODEL=openai:gpt-4o-mini` (or anthropic:, ollama:, bedrock_converse:) | `pip install langchain langchain-openai` |
| `crewai_crew.py` | CrewAI | a team: Sourcer → Screener, each with a role and tools | `CREW_LLM=openai/gpt-4o-mini` (any LiteLLM string, e.g. `ollama/qwen2.5:7b`) | `pip install crewai` |
| `strands_agent.py` | Strands Agents (AWS) | `Agent(model, tools)`; can load tools from your MCP server with `--mcp` | `MODEL=bedrock` (default), `ollama` or `openai` | `pip install strands-agents` |

And without any framework: `challenge/mcp_server.py` gives the same tools to Claude Code or Kiro
(see `.mcp.json`, `.kiro/settings/mcp.json` and the `hiring-agent` agent).
To build an MCP server step by step, live: `challenge/mcp_live/README.md`.

## Try

```bash
python challenge/frameworks/langgraph_agentic_rag.py "Who has worked with n8n?"
LC_MODEL=ollama:qwen2.5:7b python challenge/frameworks/langchain_agent.py "Who knows Kafka?"
CREW_LLM=ollama/qwen2.5:7b python challenge/frameworks/crewai_crew.py backend-engineer
MODEL=ollama python challenge/frameworks/strands_agent.py --mcp "Shortlist 3 candidates for the AI engineer job"
```

Local models must support tool calling (qwen2.5, llama3.1 and later). Small models make more mistakes
choosing tools: that is a good thing to observe and discuss.
