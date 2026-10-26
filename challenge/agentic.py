"""
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

HOW TO WORK: this file already runs. The starter nodes copy NAIVE RAG (route always says SEARCH,
grade always says RELEVANT), so with "Agentic" ticked you get the same score as before.
Replace ONE node at a time, press "Reload pipeline", run Verify with "Agentic" ticked, compare:
  5A route   →  list questions        5B grade    →  "not in the CVs" questions
  5C rewrite →  weak searches         5D understand → follow-up questions
Edit only the nodes. The graph at the bottom (the edges) can stay as it is.
Stuck? cp challenge/checkpoints/agentic_done.py challenge/agentic.py
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
# ---------------------------------------------------------------- 5D · understand (follow-ups)
# Prompt idea: "In challenge/agentic.py implement understand(): if there is history, ask llm() to rewrite
#  the follow-up so it stands alone (replace he/she/they using the earlier question). If the model's
#  answer is too short, join the earlier question and the follow-up. Add one line to steps."
def understand(s: State) -> State:
    q = pipeline.make_query(s["question"], s.get("history", []))       # STARTER: your level-4 make_query
    return {"query": q, "steps": [f"understand · search for “{q}” (starter: your make_query)"]}


# ---------------------------------------------------------------- 5A · route (list or search?)
# Prompt idea: "In challenge/agentic.py implement route(): ask llm() with a few-shot prompt whether the
#  question is LIST (wants every candidate with a skill, tool, city, degree) or SEARCH (one fact).
#  For LIST, ask llm() for the term to look for (1-3 words) and return it as 'term'.
#  Small models need examples in the prompt. Add one line to steps."
def route(s: State) -> State:
    return {"kind": "search", "steps": ["route · always SEARCH (starter: 5A not done)"]}       # STARTER


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


# ---------------------------------------------------------------- 5B · grade (is it relevant?)
# Prompt idea: "In challenge/agentic.py implement grade(): score the hits with
#  helpers.relevance(query, texts), keep the best score in 'best', and set verdict 'relevant' if
#  best >= RELEVANT, else 'weak'. Add one line to steps with the score."
def grade(s: State) -> State:
    return {"verdict": "relevant", "steps": ["grade · always RELEVANT (starter: 5B not done)"]}  # STARTER


# ---------------------------------------------------------------- 5C · rewrite (try again)
# Prompt idea: "In challenge/agentic.py implement rewrite(): ask llm() for a better search query for a
#  CV database (key skills, tools, job titles, companies, synonyms) from the question and the last
#  query. Return it as 'query'. Add one line to steps."
def rewrite(s: State) -> State:
    return {"query": s["query"], "steps": ["rewrite · same query again (starter: 5C not done)"]}  # STARTER


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
