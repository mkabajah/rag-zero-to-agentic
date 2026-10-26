"""
THE HIRING AGENT IN STRANDS AGENTS (AWS) · the model decides which tool to call, in a loop.

    pip install strands-agents
    python challenge/frameworks/strands_agent.py "Shortlist 3 candidates for the backend job"

Model (pick one with MODEL):
    MODEL=bedrock   (default) Amazon Bedrock with your AWS credentials, Strands' default model
    MODEL=ollama    a local Ollama model: OLLAMA_MODEL=qwen2.5:7b (needs a model that can call tools)
    MODEL=openai    any OpenAI-compatible API: OPENAI_API_KEY, OPENAI_MODEL

Two ways to give the agent your RAG:  (1) Python tools (below) · (2) your MCP server (--mcp).
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from strands import Agent, tool  # noqa: E402

import agent_tools as T  # noqa: E402


# (1) RAG as Python tools: the docstring is what the model reads to decide when to call it.
@tool
def search_cvs(question: str) -> list:
    """Search the candidate CVs for one focused question. Returns passages with their CV file name.

    Args:
        question: one skill, project, company or certificate to look for
    """
    return T.search_cvs(question)


@tool
def find_candidates(skill: str = "", city: str = "") -> list:
    """List EVERY candidate whose CV mentions a skill and/or a city (not limited to top-K).

    Args:
        skill: a skill such as "kafka" or "power bi"
        city: a city such as "haifa"
    """
    return T.find_candidates(skill, city)


@tool
def get_cv(file_name: str) -> dict:
    """Return the full text of one CV (contact details removed), to check the evidence.

    Args:
        file_name: the CV file name returned by the other tools
    """
    return T.get_cv(file_name)


@tool
def list_jobs() -> list:
    """The open positions with their must-have and nice-to-have requirements."""
    return T.list_jobs()


def model():
    kind = os.getenv("MODEL", "bedrock")
    if kind == "ollama":
        from strands.models.ollama import OllamaModel
        return OllamaModel(host="http://localhost:11434", model_id=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"))
    if kind == "openai":
        from strands.models.openai import OpenAIModel
        return OpenAIModel(model_id=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    return None                                   # None = Strands' default Bedrock model


if __name__ == "__main__":
    ask = " ".join(a for a in sys.argv[1:] if a != "--mcp") or "Shortlist 3 candidates for the backend job, with evidence."
    if "--mcp" in sys.argv:
        # (2) the SAME tools through your MCP server: write a tool once, use it from any client.
        from mcp import StdioServerParameters, stdio_client
        from strands.tools.mcp import MCPClient
        server = MCPClient(lambda: stdio_client(StdioServerParameters(
            command=sys.executable, args=[str(pathlib.Path(__file__).resolve().parents[1] / "mcp_server.py")])))
        with server:
            agent = Agent(model=model(), tools=server.list_tools_sync(), system_prompt=T.SYSTEM_PROMPT)
            agent(ask)
    else:
        agent = Agent(model=model(), tools=[search_cvs, find_candidates, get_cv, list_jobs], system_prompt=T.SYSTEM_PROMPT)
        agent(ask)
