"""
AGENTIC RAG AS A GRAPH (LangGraph) · runs on your laptop with the local model, no API key.

    pip install langgraph
    python challenge/frameworks/langgraph_agentic_rag.py "Who has worked with n8n?"

The graph:   START → retrieve → grade ─(good)─────────→ generate → END
                         ↑          └─(weak, < 2 tries)→ rewrite ─┘ (back to retrieve)
retrieve uses YOUR pipeline (challenge/agent_tools.search_cvs). grade asks the LLM whether the
passages answer the question. rewrite asks the LLM for a better search query. Every step is a
node you can print, test and change: that is the point of a graph.
"""
import pathlib
import sys
from typing import TypedDict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from langgraph.graph import END, START, StateGraph  # noqa: E402

import agent_tools as T  # noqa: E402
from helpers import llm  # noqa: E402


class State(TypedDict, total=False):
    question: str      # what the user asked
    query: str         # what we search for (rewritten on a retry)
    passages: list     # what retrieval returned
    tries: int
    verdict: str
    answer: str


def retrieve(s: State) -> State:
    hits = T.search_cvs(s.get("query") or s["question"])
    print(f"  retrieve  ({s.get('query') or s['question']!r}) -> {[h.get('cv', 'none') for h in hits]}")
    return {"passages": hits, "tries": s.get("tries", 0) + 1}


def grade(s: State) -> State:
    if any("note" in h for h in s["passages"]):
        return {"verdict": "nothing"}
    ctx = "\n".join(f"- ({h['cv']}) {h['text'][:300]}" for h in s["passages"])
    v = llm("Answer only YES or NO.", f"Do these passages contain the answer?\nQuestion: {s['question']}\nPassages:\n{ctx}", 3)
    verdict = "good" if "YES" in v.upper() else "weak"
    print(f"  grade     -> {verdict}")
    return {"verdict": verdict}


def route(s: State) -> str:
    if s["verdict"] == "good" or s["tries"] >= 2:
        return "generate"
    return "rewrite" if s["verdict"] == "weak" else "generate"


def rewrite(s: State) -> State:
    q = llm("Rewrite the question as a short search query with the key skills and words. Reply with the query only.",
            s["question"], 40).strip().strip('"')
    print(f"  rewrite   -> {q!r}")
    return {"query": q}


def generate(s: State) -> State:
    if s["verdict"] == "nothing":
        return {"answer": "I don't know based on the CVs."}
    ctx = "\n\n".join(f"[{i}] ({h['cv']}) {h['text']}" for i, h in enumerate(s["passages"], 1))
    return {"answer": llm(T.SYSTEM_PROMPT, f"CV passages:\n{ctx}\n\nQuestion: {s['question']}", 250)}


g = StateGraph(State)
for name, fn in [("retrieve", retrieve), ("grade", grade), ("rewrite", rewrite), ("generate", generate)]:
    g.add_node(name, fn)
g.add_edge(START, "retrieve")
g.add_edge("retrieve", "grade")
g.add_conditional_edges("grade", route, {"generate": "generate", "rewrite": "rewrite"})
g.add_edge("rewrite", "retrieve")
g.add_edge("generate", END)
agent = g.compile()

if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Who has worked with n8n?"
    print(f"Question: {question}")
    out = agent.invoke({"question": question})
    print("\nAnswer:\n" + out["answer"])
