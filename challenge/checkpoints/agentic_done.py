"""
CHECKPOINT · LEVEL 5 done: the agentic RAG graph with every node filled in.
Behind? Copy it over your file:   cp challenge/checkpoints/agentic_done.py challenge/agentic.py
then press "Reload pipeline" in the app and tick "Agentic".

LEVEL 5 · AGENTIC RAG · your chatbot becomes a small agent, built with LangGraph.

Naive RAG always does the same thing: search once, answer. This graph DECIDES at every step:

  START → understand → route ──LIST────→ find_all ──(found)──────────────→ answer → END
                         │                   └─(nothing)──→ refuse → END      ↑
                         └──SEARCH→ retrieve → grade ──(relevant)───────────────┘
                                       ↑         ├──(weak, tries < 2)→ rewrite ─┐
                                       └─────────┼──────────────────────────────┘
                                                 └──(weak after 2 tries)→ refuse → END

  understand  a follow-up ("which hospital did HE…") → rewrite it so it stands alone   (LLM)
  route       LIST question (every candidate with X) or SEARCH (one fact)?            (LLM)
  find_all    LIST: scan EVERY CV for the term, not only the top-K                    (a tool)
  retrieve    SEARCH: your pipeline.retrieve()                                        (a tool)
  grade       is what we found relevant? the cross-encoder scores it                  (a model)
  rewrite     not relevant: write a better search query, try again                   (LLM)
  answer      your build_prompt() + the LLM        refuse   "I don't know based on the CVs."
"""
import operator
import re
import time
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

import pipeline
from helpers import llm, relevance

MAX_TRIES = 2          # searches before the agent gives up
RELEVANT = -6.0        # cross-encoder score that counts as "relevant" (chosen on the practice questions)
DOCS = {}              # file name -> full CV text, filled by setup() when the app builds your pipeline


class State(TypedDict, total=False):
    question: str                              # what the user typed
    history: list                              # the earlier questions in this chat
    generate: bool                             # False = retrieval only (fast Verify)
    query: str                                 # what we search for
    kind: str                                  # "list" or "search"
    term: str                                  # the thing a LIST question looks for
    hits: list                                 # passages found
    best: float                                # best relevance score so far
    tries: int                                 # searches so far
    verdict: str                               # "relevant" or "weak"
    answer: str
    prompt: str
    steps: Annotated[list, operator.add]       # the trace: every node adds one line


def setup(docs):
    """Called by the app after LEVEL 1: gives the tools the full text of every CV."""
    DOCS.clear()
    DOCS.update({d["source"]: re.sub(r"\s+", " ", d["text"]) for d in docs})


# ================================================================= the nodes
UNDERSTAND = ("Rewrite the follow-up question so it can be understood alone. Replace he, she, they, him, her "
              "with who they are, using the earlier question. Reply with the question only.")


def understand(s: State) -> State:
    if not s.get("history"):
        return {"query": s["question"], "steps": ["understand · no earlier question: it stands alone"]}
    q = llm(UNDERSTAND, f"Earlier question: {s['history'][-1]}\nFollow-up: {s['question']}\nStand-alone question:", 60)
    q = q.strip().strip('"').splitlines()[0] if q.strip() else ""
    if len(q) < 8:                                         # the small model failed: join the two questions
        q = f"{s['history'][-1]} {s['question']}"
    return {"query": q, "steps": [f"understand · follow-up → “{q}”"]}


ROUTE = ("You sort questions about job candidates into two kinds.\n"
         "LIST = the question wants EVERY candidate who has something (a skill, a tool, a city, a degree).\n"
         "SEARCH = the question asks about one specific fact, person, project or company.\n"
         "Examples:\nWhich candidates know Java? -> LIST\nWho has a PhD? -> LIST\nWhich candidates live in Haifa? -> LIST\n"
         "Who built a chatbot for a bank? -> SEARCH\nWhich candidate worked at Intel as an intern? -> SEARCH\n"
         "What did she study? -> SEARCH\nReply with one word: LIST or SEARCH.")
TERM = ("Extract what the question is looking for, as 1 to 3 words that would appear in a CV.\nExamples:\n"
        "Which candidates know Kafka? -> Kafka\nWho is based in Tel Aviv? -> Tel Aviv\n"
        "Which candidates have Power BI experience? -> Power BI\nReply with the words only.")


def route(s: State) -> State:
    kind = "list" if "LIST" in llm(ROUTE, f"{s['query']} ->", 4).upper() else "search"
    if kind == "search":
        return {"kind": kind, "steps": ["route · SEARCH: one fact → use the vector search"]}
    term = llm(TERM, f"{s['query']} ->", 8).strip().strip('".').splitlines()[0]
    return {"kind": kind, "term": term, "steps": [f"route · LIST: every candidate with “{term}” → scan all CVs"]}


def find_all(s: State) -> State:
    pat = re.compile(rf"(?<![a-z0-9]){re.escape(s['term'].lower())}(?![a-z0-9])")
    hits = []
    for name, text in DOCS.items():
        m = pat.search(text.lower())
        if m:
            a = max(0, m.start() - 200)
            hits.append({"rank": len(hits) + 1, "source": name, "text": text[a:a + 500], "score": 1.0, "via": "agent · find_all"})
    return {"hits": hits, "steps": [f"find_all · “{s['term']}” is in {len(hits)} of {len(DOCS)} CVs"]}


def retrieve(s: State) -> State:
    hits = pipeline.retrieve(s["query"], pipeline.K)
    return {"hits": [dict(h, via="agent · retrieve") for h in hits], "tries": s.get("tries", 0) + 1,
            "steps": [f"retrieve · search {s.get('tries', 0) + 1}: “{s['query']}” → {', '.join(h['source'] for h in hits)}"]}


def grade(s: State) -> State:
    best = max(relevance(s["query"], [h["text"] for h in s["hits"]]), default=-99)
    verdict = "relevant" if best >= RELEVANT else "weak"
    return {"best": best, "verdict": verdict, "steps": [f"grade · best relevance {best:.1f} → {verdict.upper()}"]}


REWRITE = ("The search found nothing relevant. Write a better search query for a CV database: "
           "the key skills, tools, job titles and companies, with synonyms. Reply with the query only.")


def rewrite(s: State) -> State:
    q = llm(REWRITE, f"Question: {s['question']}\nLast query: {s['query']}\nBetter query:", 40).strip().strip('"').splitlines()[0]
    return {"query": q or s["query"], "steps": [f"rewrite · new query → “{q}”"]}


def answer(s: State) -> State:
    if s.get("kind") == "list":                            # the tool already has the full list: show it, with evidence
        term = s["term"].lower()
        lines = []
        for h in s["hits"]:
            i = h["text"].lower().find(term)
            quote = h["text"][max(0, i - 60):i + len(term) + 60].strip() if i >= 0 else h["text"][:120]
            lines.append(f"- **{h['source']}**: “…{quote}…”")
        return {"prompt": "", "answer": f"{len(s['hits'])} CVs mention “{s['term']}”:\n" + "\n".join(lines),
                "steps": [f"answer · list all {len(s['hits'])} CVs, each with the line that proves it (no LLM needed)"]}
    prompt = pipeline.build_prompt(s["query"], s["hits"])
    if not s.get("generate", True):
        return {"prompt": prompt, "answer": "(answers off: retrieval only)", "steps": ["answer · (generation off)"]}
    return {"prompt": prompt, "answer": llm(pipeline.SYSTEM_PROMPT, prompt, 300), "steps": ["answer · the LLM writes it from the passages"]}


def refuse(s: State) -> State:
    return {"hits": [], "answer": pipeline.REFUSAL, "steps": ["refuse · nothing relevant: say “I don't know” instead of guessing"]}


# ================================================================= the edges (the decisions)
def after_route(s: State) -> str:
    return "find_all" if s["kind"] == "list" else "retrieve"


def after_find_all(s: State) -> str:
    return "answer" if s["hits"] else "refuse"


def after_grade(s: State) -> str:
    if s["verdict"] == "relevant":
        return "answer"
    return "rewrite" if s["tries"] < MAX_TRIES else "refuse"


g = StateGraph(State)
for name, fn in [("understand", understand), ("route", route), ("find_all", find_all), ("retrieve", retrieve),
                 ("grade", grade), ("rewrite", rewrite), ("answer", answer), ("refuse", refuse)]:
    g.add_node(name, fn)
g.add_edge(START, "understand")
g.add_edge("understand", "route")
g.add_conditional_edges("route", after_route, ["find_all", "retrieve"])
g.add_conditional_edges("find_all", after_find_all, ["answer", "refuse"])
g.add_edge("retrieve", "grade")
g.add_conditional_edges("grade", after_grade, ["answer", "rewrite", "refuse"])
g.add_edge("rewrite", "retrieve")
g.add_edge("answer", END)
g.add_edge("refuse", END)
graph = g.compile()


# ================================================================= run it (the app calls this)
def run(question, history=(), generate=True):
    """Run the graph and return what the app shows: the path, every step, the hits and the answer."""
    state, path, t0 = {"question": question, "history": list(history), "generate": generate, "steps": []}, [], time.perf_counter()
    for update in graph.stream(state, stream_mode="updates"):
        for node, change in update.items():
            path.append(node)
            for k, v in (change or {}).items():
                state[k] = state.get(k, []) + v if k == "steps" else v
    return {**state, "path": path, "ms": (time.perf_counter() - t0) * 1000}
