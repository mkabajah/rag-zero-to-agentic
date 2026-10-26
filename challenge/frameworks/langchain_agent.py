"""
THE HIRING AGENT IN LANGCHAIN 1.x · create_agent = the model + your tools in a ReAct loop.

    pip install langchain langchain-anthropic        # or langchain-openai, langchain-aws, langchain-ollama
    LC_MODEL=anthropic:claude-sonnet-4-5 python challenge/frameworks/langchain_agent.py "Who knows Kafka?"

LC_MODEL is "<provider>:<model>", e.g. "openai:gpt-4o-mini", "bedrock_converse:<model id>",
"ollama:qwen2.5:7b". Set the provider's API key.
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from langchain.agents import create_agent  # noqa: E402
from langchain.tools import tool  # noqa: E402

import agent_tools as T  # noqa: E402

# RAG as a tool: wrap the plain functions; the docstrings become the tool descriptions.
tools = [tool(T.search_cvs), tool(T.find_candidates), tool(T.get_cv), tool(T.list_jobs)]

agent = create_agent(model=os.getenv("LC_MODEL", "openai:gpt-4o-mini"), tools=tools, system_prompt=T.SYSTEM_PROMPT)

if __name__ == "__main__":
    ask = " ".join(sys.argv[1:]) or "Shortlist 3 candidates for the AI engineer job, with evidence."
    result = agent.invoke({"messages": [{"role": "user", "content": ask}]})
    for m in result["messages"]:                       # every step of the loop: tool calls and results
        print(f"[{m.type}]", (m.content if isinstance(m.content, str) else m.content)[:400] if m.content else m.tool_calls)
