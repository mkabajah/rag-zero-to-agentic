"""
MCP LIVE · STEP 2 · your local vector DB (Chroma) as an MCP tool.

The chatbot already built the index: challenge/chroma_db/ is a Chroma database ON YOUR DISK
(collection "cvs", one vector per chunk, MiniLM embeddings). This server does not rebuild it:
it opens the same database and searches it. Same embedding model for the question, or the
vectors don't match.

    python challenge/mcp_live/client.py challenge/mcp_live/step2_search.py search_cvs '{"question": "Who knows Kafka?"}'
    claude mcp add cv-search -- .venv/bin/python challenge/mcp_live/step2_search.py
"""
import contextlib
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parents[1]          # challenge/
sys.path.insert(0, str(HERE))

import chromadb                                           # noqa: E402
from mcp.server.fastmcp import FastMCP                    # noqa: E402

with contextlib.redirect_stdout(sys.stderr):              # stdout belongs to the MCP protocol
    from helpers import embed
    embed(["warm up"])                                    # load MiniLM now, not on the first question

DB = chromadb.PersistentClient(path=str(HERE / "chroma_db"))
mcp = FastMCP("cv-search")


@mcp.tool()
def search_cvs(question: str, k: int = 5) -> list[dict]:
    """Search the candidate CVs for one focused question (a skill, a project, a company).
    Returns the k most similar CV passages with their file name and similarity score.
    Call it several times with short questions rather than once with a long one."""
    cvs = DB.get_collection("cvs")                        # fetched each call: the app may rebuild it
    with contextlib.redirect_stdout(sys.stderr):
        vec = embed([question]).tolist()
    res = cvs.query(query_embeddings=vec, n_results=k)
    return [{"cv": m["source"], "score": round(1 - d, 3), "text": doc[:700]}
            for doc, m, d in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])]


if __name__ == "__main__":
    mcp.run()
