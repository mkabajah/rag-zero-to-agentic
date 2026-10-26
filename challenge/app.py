"""
CV CHATBOT · the app (you don't need to edit this file: you build challenge/pipeline.py)

    python challenge/app.py          →  http://127.0.0.1:7862

Put the CVs in challenge/cvs/ (PDF, DOCX, TXT or MD). That folder is ignored by git: real CVs
never go to GitHub.

  Status box   which levels of your pipeline work, and what to do next
  📄 Data      your ingestion: every CV, its size, its chunks (LEVEL 1)
  💬 Chat      ask questions: what was searched, what came back and how, the exact prompt, the output
  ✅ Verify    upload a questions JSON, run them all: Hit@K, Recall@K, MRR, refusals, one row per question
  🕸 Graph     the knowledge graph your STEP 7 builds
  🤖 Agentic   tick "Agentic RAG" in Chat or Verify: your LEVEL 5 graph (challenge/agentic.py) runs instead,
               and "Agent steps" shows every decision it made

Press "Reload pipeline" after every change to pipeline.py: no need to restart the app.
"""
import importlib
import json
import os
import pathlib
import sys
import time
import traceback

import gradio as gr
import matplotlib
import networkx as nx
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import helpers                    # noqa: E402
import pipeline                   # noqa: E402

try:
    import agentic                # LEVEL 5 · needs: pip install langgraph
    AGENTIC_ERR = ""
except Exception as e:            # noqa: BLE001
    agentic, AGENTIC_ERR = None, f"{type(e).__name__}: {e}"

CV_DIR = pathlib.Path(os.getenv("CV_DIR", HERE / "cvs"))
STATE = {"docs": [], "chunks": [], "graph": nx.Graph(), "levels": {}, "index_ms": 0}


# ================================================================= build the pipeline, level by level
def first_line_of(err):
    return str(err).splitlines()[0] if str(err) else type(err).__name__


def build():
    """Run LEVEL 1, 2, 3 of the student's pipeline and record what works."""
    global agentic, AGENTIC_ERR
    importlib.reload(pipeline)
    try:
        import agentic as _a
        agentic, AGENTIC_ERR = importlib.reload(_a), ""
    except Exception as e:        # noqa: BLE001
        agentic, AGENTIC_ERR = None, f"{type(e).__name__}: {first_line_of(e)}"
    lv = {}
    STATE.update(docs=[], chunks=[], graph=nx.Graph())
    try:
        docs = pipeline.load_cvs(CV_DIR)
        assert docs, f"no CVs found in {CV_DIR}"
        chunks = [c for d in docs for c in pipeline.chunk(d)]
        assert chunks, "chunk() returned no chunks"
        STATE.update(docs=docs, chunks=chunks)
        if agentic:
            agentic.setup(docs)
        lv[1] = (True, f"{len(docs)} CVs → {len(chunks)} chunks")
    except Exception as e:
        lv[1] = (False, first_line_of(e))
    if lv[1][0]:
        try:
            t = time.perf_counter()
            n = pipeline.build_index(STATE["chunks"])
            STATE["index_ms"] = (time.perf_counter() - t) * 1000
            lv[2] = (True, f"{n} chunks stored in {STATE['index_ms'] / 1000:.1f} s")
        except Exception as e:
            lv[2] = (False, first_line_of(e))
    if lv.get(2, (False,))[0]:
        try:
            hits = pipeline.retrieve("python experience", pipeline.K)
            pipeline.build_prompt("test", hits)
            assert hits and "source" in hits[0] and "text" in hits[0], "retrieve() must return dicts with source and text"
            lv[3] = (True, f"retrieve returns {len(hits)} chunks · naive RAG works: run Verify")
        except Exception as e:
            lv[3] = (False, first_line_of(e))
    try:
        g = pipeline.build_graph(STATE["chunks"]) if STATE["chunks"] else nx.Graph()
        STATE["graph"] = g if g is not None else nx.Graph()
    except Exception as e:
        print("build_graph failed:", e)
    STATE["levels"] = lv
    return status_md()


def status_md():
    names = {1: "Ingest (load_cvs, chunk)", 2: "Index (build_index · Chroma)", 3: "Answer (retrieve, build_prompt)"}
    rows = []
    for n in (1, 2, 3):
        ok, msg = STATE["levels"].get(n, (None, "waiting for the level before"))
        icon = "✅" if ok else ("❌" if ok is False else "⬜")
        rows.append(f"| {icon} | LEVEL {n} · {names[n]} | {msg} |")
    g = STATE["graph"]
    rows.append(f"| {'✅' if g.number_of_nodes() else '⬜'} | STEP 7 · Graph | "
                + (f"{g.number_of_nodes()} nodes, {g.number_of_edges()} edges" if g.number_of_nodes() else "not built yet") + " |")
    rows.append(agentic_status_row())
    return "| | Level | Status |\n|---|---|---|\n" + "\n".join(rows) + f"\n\nCVs folder: `{CV_DIR}` · K = {pipeline.K}"


AGENT_NODES = [("5A", "route"), ("5B", "grade"), ("5C", "rewrite"), ("5D", "understand")]


def agentic_status_row():
    if agentic is None:
        return f"| ❌ | LEVEL 5 · Agentic graph | {AGENTIC_ERR or 'challenge/agentic.py not found'} |"
    import inspect
    todo = [f"{k} {n}" for k, n in AGENT_NODES if "starter" in inspect.getsource(getattr(agentic, n)).lower()]
    if len(todo) == len(AGENT_NODES):
        return "| ⬜ | LEVEL 5 · Agentic graph | runs like naive RAG (all starter nodes): start with 5A route |"
    done = len(AGENT_NODES) - len(todo)
    return (f"| {'✅' if not todo else '🟡'} | LEVEL 5 · Agentic graph | {done}/{len(AGENT_NODES)} nodes are yours"
            + (f" · still starter: {', '.join(todo)}" if todo else " · tick Agentic in Verify and compare") + " |")


def level_ok(n):
    return STATE["levels"].get(n, (False,))[0]


# ================================================================= one RAG turn
def rag(question, history, generate=True):
    t = {"question": question, "query": question, "hits": [], "prompt": "", "refused": False,
         "search_ms": 0, "answer_ms": 0, "prompt_tokens": 0}
    if not level_ok(3):
        first = next((n for n in (1, 2, 3) if not level_ok(n)), 3)
        t["answer"] = f"LEVEL {first} is not done yet: see the status box, fix challenge/pipeline.py, press Reload pipeline."
        return t
    t0 = time.perf_counter()
    try:
        t["query"] = pipeline.make_query(question, history)
        hits = pipeline.retrieve(t["query"], pipeline.K)
        t["refused"] = bool(pipeline.should_refuse(t["query"], hits))
        t["hits"] = [] if t["refused"] else hits
        t["prompt"] = "" if t["refused"] else pipeline.build_prompt(question, hits)
    except Exception as e:
        t["answer"] = f"Your pipeline raised an error: {first_line_of(e)}\n\n{traceback.format_exc(limit=3)}"
        return t
    t["search_ms"] = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    if t["refused"]:
        t["answer"] = pipeline.REFUSAL
    elif generate:
        t["answer"] = helpers.llm(pipeline.SYSTEM_PROMPT, t["prompt"], 300)
    else:
        t["answer"] = "(answers off: retrieval only)"
    t["answer_ms"] = (time.perf_counter() - t1) * 1000
    t["prompt_tokens"] = int(len((pipeline.SYSTEM_PROMPT + t["prompt"]).split()) * 1.3)
    return t


def rag_agentic(question, history, generate=True):
    """One turn through the LEVEL 5 graph. Returns the same fields as rag(), plus the path and the steps."""
    if agentic is None:
        return {"question": question, "query": question, "hits": [], "prompt": "", "refused": False, "search_ms": 0,
                "answer_ms": 0, "prompt_tokens": 0, "path": [], "steps": [],
                "answer": f"LEVEL 5 is not available: {AGENTIC_ERR}. Run: pip install langgraph"}
    if not level_ok(3):
        return rag(question, history, generate)
    try:
        r = agentic.run(question, history, generate)
    except Exception as e:  # noqa: BLE001
        return {"question": question, "query": question, "hits": [], "prompt": "", "refused": False, "search_ms": 0,
                "answer_ms": 0, "prompt_tokens": 0, "path": [], "steps": [],
                "answer": f"Your agentic.py raised an error: {first_line_of(e)}\n\n{traceback.format_exc(limit=3)}"}
    answer = r.get("answer", "")
    return {"question": question, "query": r.get("query", question), "hits": r.get("hits", []), "prompt": r.get("prompt", ""),
            "refused": answer.strip() == pipeline.REFUSAL, "answer": answer, "search_ms": r.get("ms", 0), "answer_ms": 0,
            "prompt_tokens": int(len((pipeline.SYSTEM_PROMPT + r.get("prompt", "")).split()) * 1.3),
            "path": r.get("path", []), "steps": r.get("steps", [])}


# the picture of the LEVEL 5 graph: where every node sits, and which path a question took
POS = {"__start__": (0, 0), "understand": (1.2, 0), "route": (2.4, 0), "find_all": (3.8, 1.1), "retrieve": (3.8, -1.1),
       "grade": (5.2, -1.1), "rewrite": (5.2, -2.3), "answer": (6.6, 0), "refuse": (6.6, -2.3), "__end__": (7.8, -1.1)}


def draw_agent(path=()):
    fig, ax = plt.subplots(figsize=(9.5, 3.6))
    ax.axis("off")
    if agentic is None:
        ax.text(0.5, 0.5, "LEVEL 5 not loaded: pip install langgraph", ha="center")
        return fig
    walk = ["__start__"] + list(path) + ["__end__"]
    taken = set(zip(walk, walk[1:]))
    gg = agentic.graph.get_graph()
    for e in gg.edges:
        a, b = POS.get(e.source), POS.get(e.target)
        if not a or not b:
            continue
        on = (e.source, e.target) in taken
        ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="-|>", lw=2.6 if on else 1.0,
                    color="#0B6F68" if on else "#C9C3B4", linestyle="-" if on or not e.conditional else "--",
                    shrinkA=26, shrinkB=26, connectionstyle="arc3,rad=0.25" if (e.source, e.target) == ("rewrite", "retrieve") else "arc3"))
    for n in gg.nodes:
        if n not in POS:
            continue
        x, y = POS[n]
        on = n in walk
        label = {"__start__": "START", "__end__": "END"}.get(n, n)
        ax.text(x, y, label, ha="center", va="center", fontsize=10, fontweight="bold", color="white" if on else "#6B7685",
                bbox=dict(boxstyle="round,pad=0.5", fc="#0E1B2C" if on else "#F1EEE5", ec="#0B6F68" if on else "#D9D4C5", lw=1.5))
    for i, n in enumerate(path, 1):
        if n in POS:
            ax.text(POS[n][0] + 0.38, POS[n][1] + 0.32, str(i), fontsize=8, color="#8A5A0A", fontweight="bold")
    ax.set_xlim(-0.6, 8.4)
    ax.set_ylim(-2.9, 1.7)
    fig.tight_layout()
    return fig


def steps_md(t):
    if not t.get("path"):
        return "Tick **Agentic RAG** and ask: every decision of your LEVEL 5 graph shows up here."
    rows = "\n".join(f"| {i} | {line.split(' · ', 1)[0]} | {line.split(' · ', 1)[-1]} |" for i, line in enumerate(t["steps"], 1))
    return (f"**Path:** {' → '.join(t['path'])} · {len(t['path'])} steps · {t['search_ms'] / 1000:.1f} s\n\n"
            f"| # | node | what it did |\n|---|---|---|\n{rows}")


def hit_rows(hits, expected=None):
    rows = []
    for h in hits:
        row = [h.get("rank", ""), h.get("source", ""), round(float(h.get("score", 0)), 3), h.get("via", "vector")]
        if expected is not None:
            row.append("✓ expected" if matches(h.get("source", ""), expected) else "")
        rows.append(row + [h.get("text", "")[:300]])
    return rows


# ================================================================= VERIFY (evaluation)
def load_questions(path):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return data["questions"] if isinstance(data, dict) else data


def matches(source, expected):
    s = source.lower()
    return any(e.lower() in s or pathlib.Path(e).stem.lower() in s for e in expected)


def score(item, t):
    expected = item.get("expected", [])
    if item.get("refuse"):
        ok = t["refused"] or pipeline.REFUSAL.lower() in t["answer"].lower()
        return {"pass": ok, "hit": None, "recall": None, "rr": None, "note": "refused ✓" if ok else "answered, should refuse ✗"}
    found = {e for e in expected for h in t["hits"] if matches(h.get("source", ""), [e])}
    ranks = [h.get("rank", i) for i, h in enumerate(t["hits"], 1) if matches(h.get("source", ""), expected)]
    recall = len(found) / len(expected) if expected else 0
    words = item.get("answer_contains", [])
    answer_ok = all(w.lower() in t["answer"].lower() for w in words) if words and t["answer"][:1] != "(" else None
    ok = recall == 1 and answer_ok is not False
    note = f"{len(found)}/{len(expected)} CVs found" + ("" if answer_ok is None else (" · answer ✓" if answer_ok else " · answer ✗"))
    return {"pass": ok, "hit": bool(ranks), "recall": recall, "rr": 1 / min(ranks) if ranks else 0, "note": note}


def run_verify(file, generate, use_agent=False, progress=gr.Progress()):
    if file is None:
        return "Upload a questions JSON first.", None, gr.update(choices=[]), None, {}
    if not level_ok(3):
        return "Finish LEVEL 1–3 first (see the status box): Verify needs a working naive RAG.", None, gr.update(choices=[]), None, {}
    items, traces, rows = load_questions(file), {}, []
    for item in progress.tqdm(items, desc="Running questions"):
        t = (rag_agentic if use_agent else rag)(item["question"], item.get("history", []), generate)
        s = score(item, t)
        traces[item["id"]] = {"item": item, "trace": t, "score": s}
        rows.append(["✓" if s["pass"] else "✗", item["id"], item.get("type", ""), item["question"], s["note"],
                     (" → ".join(t["path"]) + " · " if t.get("path") else "")
                     + (", ".join(h.get("source", "") for h in t["hits"]) or "(refused)")])
    vals = [v["score"] for v in traces.values()]
    ans = [s for s in vals if s["hit"] is not None]
    refusals = [s for s in vals if s["hit"] is None]
    tr = [v["trace"] for v in traces.values()]
    summary = (f"### {sum(s['pass'] for s in vals)} / {len(vals)} passed" + (" · 🤖 agentic (LEVEL 5)" if use_agent else " · naive pipeline")
               + "\n\n| Metric | Value |\n|---|---|\n"
               f"| Hit@{pipeline.K} (an expected CV is retrieved) | {sum(s['hit'] for s in ans) / max(len(ans), 1):.0%} |\n"
               f"| Recall@{pipeline.K} (share of expected CVs found) | {np.mean([s['recall'] for s in ans]) if ans else 0:.0%} |\n"
               f"| MRR (1 ÷ rank of the first right CV) | {np.mean([s['rr'] for s in ans]) if ans else 0:.2f} |\n"
               f"| Refusals correct | {sum(s['pass'] for s in refusals)} / {len(refusals)} |\n"
               f"| Avg. search / answer time | {np.mean([x['search_ms'] for x in tr]):.0f} ms / {np.mean([x['answer_ms'] for x in tr]):.0f} ms |\n"
               f"| Avg. prompt size | {np.mean([x['prompt_tokens'] for x in tr]):.0f} tokens |")
    out = HERE / "verify_results.json"
    out.write_text(json.dumps({"K": pipeline.K, "results": list(traces.values())}, indent=1, ensure_ascii=False, default=str))
    return summary, rows, gr.update(choices=list(traces), value=rows[0][1] if rows else None), str(out), traces


def show_detail(qid, traces):
    if not qid or qid not in traces:
        return "", None, "", ""
    v = traces[qid]
    t, item, s = v["trace"], v["item"], v["score"]
    head = (f"**{qid} · {item['question']}**\n\nExpected: `{', '.join(item.get('expected', [])) or 'refuse'}` · "
            f"Result: **{s['note']}** · Searched for: `{t['query']}`")
    if t.get("steps"):
        head += "\n\n" + steps_md(t)
    return head, hit_rows(t["hits"], item.get("expected", [])), f"SYSTEM:\n{pipeline.SYSTEM_PROMPT}\n\nUSER:\n{t['prompt']}", t["answer"]


# ================================================================= CHAT
def as_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return content.get("text", "")
    return " ".join(as_text(c) for c in content)


def respond(question, chat, generate, use_agent=False):
    if not question.strip():
        return "", chat, gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip()
    past = [as_text(m["content"]) for m in chat if m["role"] == "user"]
    t = (rag_agentic if use_agent else rag)(question, past, generate)
    chat = chat + [{"role": "user", "content": question}, {"role": "assistant", "content": t["answer"]}]
    query_md = (f"**You asked:** {question}\n\n**Searched for:** `{t['query']}`\n\n"
                f"Search {t['search_ms']:.0f} ms · answer {t['answer_ms']:.0f} ms · prompt {t['prompt_tokens']} tokens"
                + ("\n\n**Refused before calling the LLM.**" if t["refused"] else ""))
    return ("", chat, query_md, hit_rows(t["hits"]), f"SYSTEM:\n{pipeline.SYSTEM_PROMPT}\n\nUSER:\n{t['prompt']}", t["answer"],
            steps_md(t), draw_agent(t.get("path", [])) if use_agent else gr.skip())


# ================================================================= DATA (ingestion view)
def spaced_letters(text):
    """True when many lines come out of the PDF as single letters with spaces between them."""
    lines = [l for l in text.splitlines() if len(l.split(" ")) > 6]
    bad = [l for l in lines if sum(len(x) == 1 for x in l.split(" ")) / len(l.split(" ")) > 0.6]
    return len(bad) >= 3


def data_view():
    docs, chunks = STATE["docs"], STATE["chunks"]
    if not docs:
        return "No CVs loaded yet: LEVEL 1 (see the status box).", None, None
    per = {}
    for c in chunks:
        per[c.get("source", "?")] = per.get(c.get("source", "?"), 0) + 1
    cv_rows = [[d["source"], len(d.get("text", "")), per.get(d["source"], 0), (d.get("text", "")[:120]).replace("\n", " ")] for d in docs]
    empty = [d["source"] for d in docs if len(d.get("text", "").strip()) < 200]
    spaced = [d["source"] for d in docs if spaced_letters(d.get("text", ""))]
    md = (f"**{len(docs)} CVs · {len(chunks)} chunks · {np.mean([len(c.get('text', '')) for c in chunks]):.0f} characters per chunk on average**"
          + (f"\n\n⚠️ Almost no text in: {', '.join(empty)} (text in a Word table? a scanned PDF? your reader missed it)" if empty else "")
          + (f"\n\n⚠️ Letter-spaced text (\"P R O F I L E\") in: {', '.join(spaced)}: search cannot match these words" if spaced else ""))
    keys = sorted({k for c in chunks for k in c if k != "text"})
    ch_rows = [[str(c.get(k, "")) for k in keys] + [c.get("text", "")[:400]] for c in chunks[:60]]
    return md, cv_rows, gr.update(value=ch_rows, headers=keys + ["text"])


# ================================================================= GRAPH VIEW
COLORS = {"candidate": "#f2a33a", "skill": "#1f9e89", "city": "#3b6fb6", "company": "#8a63d2"}


def node_label(n):
    return f"{n[0]}: {n[1]}" if isinstance(n, tuple) and len(n) == 2 else str(n)


def graph_choices():
    g = STATE["graph"]
    return [node_label(n) for n in sorted(g.nodes, key=lambda n: -g.degree(n))]


def draw_graph(entity, hops):
    g = STATE["graph"]
    if g.number_of_nodes() == 0:
        return None, "**No graph yet.** Build it in STEP 7 (`build_graph` in challenge/pipeline.py), then press Reload pipeline."
    node = next((n for n in g if node_label(n) == entity), None) or max(g.nodes, key=g.degree)
    sub = nx.ego_graph(g, node, radius=int(hops))
    if sub.number_of_nodes() > 70:
        keep = [node] + sorted((n for n in sub if n != node), key=lambda n: -g.degree(n))[:69]
        sub = sub.subgraph(keep)
    fig, ax = plt.subplots(figsize=(11, 7))
    pos = nx.spring_layout(sub, seed=7, k=1.2 / max(len(sub), 1) ** 0.5)
    kinds = [n[0] if isinstance(n, tuple) else "other" for n in sub]
    nx.draw_networkx_edges(sub, pos, ax=ax, alpha=0.35, edge_color="#7a869a")
    nx.draw_networkx_nodes(sub, pos, ax=ax, node_color=[COLORS.get(k, "#999999") for k in kinds],
                           node_size=[900 if n == node else 380 for n in sub], alpha=0.95)
    nx.draw_networkx_labels(sub, pos, ax=ax, labels={n: (n[1] if isinstance(n, tuple) else str(n)) for n in sub}, font_size=8)
    for k, c in COLORS.items():
        ax.scatter([], [], c=c, label=k)
    ax.legend(loc="lower left", frameon=False)
    ax.set_title(f"{node_label(node)} · {int(hops)} hop(s) · {sub.number_of_nodes()} nodes", fontsize=11)
    ax.axis("off")
    fig.tight_layout()
    near = sorted(node_label(n) for n in g.neighbors(node))
    return fig, f"**{node_label(node)}** is connected to {len(near)} nodes: " + ", ".join(near[:40]) + (" …" if len(near) > 40 else "")


# ================================================================= UI
def reload_all():
    s = build()
    md, cvs, chunks = data_view()
    ch = graph_choices()
    return s, md, cvs, chunks, gr.update(choices=ch, value=ch[0] if ch else None)


print("Building your pipeline…")
build()
print(status_md())

with gr.Blocks(title="CV Chatbot") as demo:
    gr.Markdown("# CV Chatbot · your RAG pipeline")
    with gr.Row():
        status = gr.Markdown(status_md())
        reload_btn = gr.Button("🔄 Reload pipeline", variant="primary", scale=0)
    with gr.Tab("📄 Data"):
        d_md = gr.Markdown()
        d_cvs = gr.Dataframe(headers=["CV", "characters", "chunks", "starts with"], wrap=True, interactive=False,
                             column_widths=["25%", "10%", "8%", "57%"])
        gr.Markdown("**The first 60 chunks** (every key you put in a chunk becomes a column)")
        d_chunks = gr.Dataframe(wrap=True, interactive=False)
    with gr.Tab("💬 Chat"):
        with gr.Row():
            with gr.Column(scale=5):
                chatbot = gr.Chatbot(height=430)
                msg = gr.Textbox(placeholder="Ask about the candidates and press Enter", show_label=False)
                generate = gr.Checkbox(value=True, label="Generate the answer with the LLM (off = retrieval only, instant)")
                use_agent = gr.Checkbox(value=False, label="🤖 Agentic RAG (LEVEL 5 · your LangGraph graph in challenge/agentic.py)")
                gr.Button("New chat").click(lambda: [], None, chatbot)
            with gr.Column(scale=6):
                query_out = gr.Markdown("Ask something to see how the answer is made.")
                with gr.Tab("🤖 Agent steps"):
                    agent_plot = gr.Plot(value=draw_agent(), show_label=False)
                    agent_steps = gr.Markdown("Tick **Agentic RAG** and ask: every decision of your LEVEL 5 graph shows up here.")
                with gr.Tab("Retrieved"):
                    hits_out = gr.Dataframe(headers=["#", "CV", "score", "found by", "chunk"], wrap=True, interactive=False,
                                            column_widths=["5%", "20%", "8%", "17%", "50%"])
                with gr.Tab("Prompt sent"):
                    prompt_out = gr.Code(language=None, label="Exactly what the LLM receives")
                with gr.Tab("Output"):
                    answer_out = gr.Markdown()
        msg.submit(respond, [msg, chatbot, generate, use_agent],
                   [msg, chatbot, query_out, hits_out, prompt_out, answer_out, agent_steps, agent_plot])
    with gr.Tab("✅ Verify"):
        traces = gr.State({})
        with gr.Row():
            qfile = gr.File(label="Questions JSON", file_types=[".json"], type="filepath")
            with gr.Column():
                vgen = gr.Checkbox(value=False, label="Also generate answers (slow on CPU; needed for answer_contains)")
                vagent = gr.Checkbox(value=False, label="🤖 Agentic RAG (LEVEL 5): run every question through your graph")
                run = gr.Button("Run all questions", variant="primary")
                download = gr.File(label="Results (JSON)")
        summary = gr.Markdown()
        results = gr.Dataframe(headers=["pass", "id", "type", "question", "result", "retrieved CVs"], wrap=True, interactive=False,
                               column_widths=["6%", "6%", "11%", "37%", "16%", "24%"])
        gr.Markdown("### Open one question")
        pick = gr.Dropdown(label="Question", choices=[])
        d_head = gr.Markdown()
        d_hits = gr.Dataframe(headers=["#", "CV", "score", "found by", "expected?", "chunk"], wrap=True, interactive=False,
                              column_widths=["5%", "18%", "7%", "15%", "10%", "45%"])
        with gr.Row():
            d_prompt = gr.Code(language=None, label="Prompt sent")
            d_answer = gr.Textbox(label="Output", lines=8)
        run.click(run_verify, [qfile, vgen, vagent], [summary, results, pick, download, traces])
        pick.change(show_detail, [pick, traces], [d_head, d_hits, d_prompt, d_answer])
    with gr.Tab("🕸 Graph"):
        gr.Markdown("The knowledge graph your STEP 7 builds. Pick a skill, city, company or candidate and see what it is connected to.")
        with gr.Row():
            g_pick = gr.Dropdown(label="Entity", choices=graph_choices(), value=(graph_choices() or [None])[0])
            g_hops = gr.Slider(1, 2, value=1, step=1, label="Hops")
            g_draw = gr.Button("Draw")
        g_plot = gr.Plot()
        g_info = gr.Markdown()
        g_draw.click(draw_graph, [g_pick, g_hops], [g_plot, g_info])
    reload_btn.click(reload_all, None, [status, d_md, d_cvs, d_chunks, g_pick])
    demo.load(data_view, None, [d_md, d_cvs, d_chunks])

if __name__ == "__main__":
    demo.launch(server_port=7862)
