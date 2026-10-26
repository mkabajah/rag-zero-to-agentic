"""
PRE-FLIGHT CHECK · run this on the demo laptop before class.

    python challenge/mcp_live/check.py            check everything
    python challenge/mcp_live/check.py --build    also (re)build the Chroma DB from challenge/cvs
    python challenge/mcp_live/check.py --llm      also load the local LLM (for the LangGraph demo)

It checks: Python, packages, the CVs, the embedding model, the local vector DB (Chroma on disk),
a test search, and that the 3 MCP servers start and answer like Claude Code would ask them.
"""
import asyncio
import contextlib
import importlib
import io
import os
import pathlib
import sys
import time
import logging

logging.getLogger("pypdf").setLevel(logging.ERROR)

HERE = pathlib.Path(__file__).resolve().parents[1]                      # challenge/
sys.path.insert(0, str(HERE))
CV_DIR = pathlib.Path(os.getenv("CV_DIR", HERE / "cvs"))
OK, BAD, WARN = "  ✓ ", "  ✗ ", "  ! "
problems = []


def say(ok, text, fix=""):
    print((OK if ok else BAD) + text + ("" if ok or not fix else f"\n      fix: {fix}"))
    if not ok:
        problems.append(text)
    return ok


print("\n1 · Python and packages")
say(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}", "use Python 3.10+ (the repo's .venv)")
for mod, pip in [("mcp", "mcp[cli]"), ("chromadb", "chromadb"), ("sentence_transformers", "sentence-transformers"),
                 ("pypdf", "pypdf"), ("docx", "python-docx"), ("networkx", "networkx")]:
    try:
        m = importlib.import_module(mod)
        say(True, f"{mod} {getattr(m, '__version__', '')}")
    except Exception as e:  # noqa: BLE001
        say(False, f"{mod} missing ({type(e).__name__})", f"pip install '{pip}'")

print("\n2 · The CVs")
files = sorted(p.name for p in CV_DIR.glob("*") if p.suffix.lower() in (".pdf", ".docx")) if CV_DIR.exists() else []
say(len(files) > 0, f"{len(files)} CVs in {CV_DIR}", "copy the CVs into challenge/cvs/ (they are not in git)")
if "Sam_Tester_CV.pdf" in files:
    say(False, "Sam_Tester_CV.pdf (the injection demo) is in the CV folder", "remove it until the security demo")

print("\n3 · The embedding model (MiniLM)")
t = time.time()
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    import helpers
    v = helpers.embed(["hello"])
kind = type(helpers._EMBEDDER).__name__
say(v.shape[1] == 384 and "Tfidf" not in kind, f"{kind}, {v.shape[1]} numbers per vector, {time.time() - t:.1f}s",
    "the model did not load and it fell back to TF-IDF: check internet / the Hugging Face cache, or set HF_HUB_OFFLINE=1")

print("\n4 · The local vector DB (Chroma on disk)")
db_path = HERE / "chroma_db"
import chromadb  # noqa: E402

if "--build" in sys.argv or not db_path.exists():
    import pipeline
    src = pipeline
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline.load_cvs(CV_DIR)
    except NotImplementedError:
        from checkpoints import level3 as src
        print("    (pipeline.py level 1–2 not done: building with checkpoints/level3.py)")
    t = time.time()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        chunks = [c for d in src.load_cvs(CV_DIR) for c in src.chunk(d)]
        n = src.build_index(chunks)
    say(n > 0, f"built {n} chunks in {time.time() - t:.1f}s")
try:
    col = chromadb.PersistentClient(path=str(db_path)).get_collection("cvs")
    n = col.count()
    sources = {m["source"] for m in col.get(include=["metadatas"])["metadatas"]}
    size = sum(f.stat().st_size for f in db_path.rglob("*") if f.is_file()) / 1e6
    say(n > 0, f"{db_path} · collection 'cvs' · {n} chunks from {len(sources)} CVs · {size:.1f} MB on disk")
    missing = sorted(set(files) - sources)
    if missing:
        print(WARN + f"{len(missing)} CV(s) have no chunks: {', '.join(missing)}\n"
              "      (usually a parsing trap: a DOCX with its text in a table, or a scanned PDF. A good thing to show!)")
    else:
        say(True, f"every CV is in the index ({len(sources)}/{len(files)})")
    res = col.query(query_embeddings=helpers.embed(["Who knows Kafka?"]).tolist(), n_results=3)
    print("    test search 'Who knows Kafka?' →", ", ".join(m["source"] for m in res["metadatas"][0]))
except Exception as e:  # noqa: BLE001
    say(False, f"no Chroma collection 'cvs' ({e})", "run: python challenge/mcp_live/check.py --build")

print("\n5 · The MCP servers (started the way Claude Code starts them)")


async def probe(server, tool, args):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=[str(server)], env=dict(os.environ))
    async with stdio_client(params, errlog=open(os.devnull, "w")) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            names = [t.name for t in (await s.list_tools()).tools]
            out = await s.call_tool(tool, args)
            return names, out.content[0].text if out.content else ""

for server, tool, args in [("mcp_live/step1_hello.py", "list_cvs", {}),
                           ("mcp_live/step2_search.py", "search_cvs", {"question": "Kafka", "k": 2}),
                           ("mcp_live/step3_full.py", "find_candidates", {"skill": "kafka"}),
                           ("mcp_server.py", "list_jobs", {})]:
    t = time.time()
    try:
        names, text = asyncio.run(asyncio.wait_for(probe(HERE / server, tool, args), 240))
        say(bool(text), f"{server:26s} tools: {', '.join(names)}  ({time.time() - t:.0f}s)")
    except Exception:  # noqa: BLE001
        fix = f"run it alone to see the error: python challenge/{server}"
        if server == "mcp_server.py":
            try:
                import pipeline
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    pipeline.chunk({"source": "x", "text": "hello"})
            except NotImplementedError:
                fix = ("it runs on YOUR challenge/pipeline.py, which is still the starter. For the demo use a finished one:\n"
                       "           cp challenge/checkpoints/level3.py challenge/pipeline.py   (or the instructor reference)")
        say(False, f"{server} did not answer", fix)

if "--llm" in sys.argv:
    print("\n6 · The local LLM (LangGraph demo)")
    t = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        a = helpers.llm("Reply with one word.", "Say OK.", 5)
    say(bool(a.strip()), f"{helpers.llm_name()} answered {a.strip()!r} in {time.time() - t:.0f}s")

print("\n" + ("ALL GOOD · ready for the live demo" if not problems else f"{len(problems)} PROBLEM(S): fix them above"))
