# The challenge · build a CV chatbot, then prove it works

You get the **app** (a Gradio UI with Data, Chat, Verify and Graph tabs). You build the **RAG
pipeline** behind it, in one file: [`pipeline.py`](pipeline.py). First the naive RAG (ingestion,
a Chroma vector DB, retrieval), then the features, one at a time, with Claude Code or Kiro.
After every change, the **Verify** tab tells you if it really got better.

```bash
git pull
pip install pypdf python-docx chromadb gradio
# put the CVs your instructor sent you in challenge/cvs/   (ignored by git: never pushed)
python challenge/app.py                    # → http://127.0.0.1:7862
```

Edit `pipeline.py`, then press **🔄 Reload pipeline** in the app (no restart). The status box at the
top shows which level works: ⬜ waiting · ❌ error (with the message) · ✅ done.

## The levels

| Level | You build (in pipeline.py) | You see it in | Prompt for Claude Code or Kiro |
|-------|-----------------------------|---------------|--------------------------------|
| **1 · Ingest** | `load_cvs(folder)`: read every PDF, DOCX, TXT · `chunk(doc)`: split into chunks | 📄 Data: every CV, its size, its chunks | "In challenge/pipeline.py implement load_cvs and chunk as their docstrings say. Use pypdf for PDF and python-docx for DOCX. Start with fixed-size chunks of 800 characters with 100 overlap. Don't change other files." |
| **2 · Index** | `build_index(chunks)`: embed every chunk and store it in **Chroma** | the status: "N chunks stored" | "Implement build_index with chromadb: a PersistentClient in HERE / 'chroma_db', delete and recreate a collection 'cvs' with cosine distance, add every chunk with its id, text, metadata and embed(texts) as embeddings. Return the count." |
| **3 · Answer** | `retrieve(query, k)`: the k nearest chunks · `build_prompt(question, hits)` | 💬 Chat works. **This is naive RAG.** Run ✅ Verify: your first score | "Implement retrieve: embed the query, query the Chroma collection for k results, return dicts with rank, source, text, score (1 - distance) and via='vector'. Implement build_prompt: number the passages [1], [2]… with their source, then the question." |
| **4 · Features** | the menu below, one step at a time | ✅ Verify after each step | see the menu |

`helpers.py` gives you `embed(texts)` (MiniLM vectors, normalized) and `llm(system, user)` (Qwen on your laptop).
**Behind?** Each level has a finished version: `cp challenge/checkpoints/level2.py challenge/pipeline.py`, then Reload.

## The menu (level 4)

| Step | Fixes | Prompt for Claude Code or Kiro | Watch in Verify |
|------|-------|--------------------------------|-----------------|
| 1 · Follow-ups | "And where did he study?" searches for nothing | "Change make_query in challenge/pipeline.py so a follow-up is rewritten into a full question using history (the earlier questions). Use llm() from helpers, with a rule-based fallback." | the `follow-up` rows |
| 2 · Better parsing and chunks | Some CVs come out empty or as "P R O F I L E"; a chunk does not say whose CV it is | "The Data tab warns about CVs with almost no text and letter-spaced text. Fix read_file: also read Word tables, and join letters that are separated by single spaces. Then put the candidate's name in front of every chunk. Show me the Data tab before and after." | the 📄 Data warnings · `exact` rows |
| 3 · Hybrid search | Exact names, tools and certificates are missed | "Add BM25 keyword search over the chunks next to the Chroma search, and merge the two lists with Reciprocal Rank Fusion (score = sum of 1/(60+rank)). ragkit/retrieval.py has a BM25 you can read." | `exact` rows |
| 4 · Rerank | The right CV is found, but not first | "Get 20 candidates, rerank them with ragkit.Reranker (its .model.predict takes (question, text) pairs) and keep the top K. Print the time it adds." | MRR, time |
| 5 · Filters | "In Haifa", "5+ years" are guessed by similarity | "At ingestion, extract each CV's name, city and years of experience into the chunk metadata. In retrieve, read a city or a minimum of years from the question and pass a Chroma where= filter." | `list` rows |
| 6 · Refusal | It always answers, even when no CV fits | "Make should_refuse return True when the best retrieved chunk is not relevant enough. Print the top score for every Verify question first, then pick a threshold and explain it." | Refusals correct |
| 7 · Graph RAG | "Which candidates know X?" has more answers than K | Three small parts, see **Step 7 in detail** below | Recall@K on `list` rows · the "found by" column · the 🕸 Graph tab |
| 8 · MCP + agent | Use your bot from Claude or Kiro | "Write challenge/mcp_server.py with FastMCP exposing search_cvs(question) and get_cv(file name), using the functions in challenge/pipeline.py. Add it to .mcp.json as cv-chatbot." | ask your agent for a shortlist |

Steps 1, 2 and 3 give the biggest wins: start there.

## Level 5 · Agentic RAG (session 3)

Your chatbot becomes a small **agent**: instead of "search once, answer", it decides at every step.
The graph is built with **LangGraph** (`pip install langgraph`) in `challenge/agentic.py`:

```
START → understand → route ──LIST────→ find_all ──(found)──────────→ answer → END
                       └──SEARCH→ retrieve → grade ──(relevant)────────↗
                                     ↑         ├──(weak, < 2 tries)→ rewrite ─┐
                                     └─────────┼──────────────────────────────┘
                                               └──(weak after 2 tries)→ refuse → END
```

The file **already runs**: its starter nodes copy naive RAG. In the app, tick **🤖 Agentic RAG** in
Chat (the *Agent steps* tab draws the path) or in Verify, then replace one node at a time:

| Node | Fixes | Prompt idea (in the file) | Watch in Verify |
|---|---|---|---|
| 5A · route | "Which candidates know X?" needs EVERY match | few-shot LLM: LIST or SEARCH, and the term | `list` rows |
| 5B · grade | it answers even when nothing fits | `helpers.relevance()` (cross-encoder) ≥ a threshold | `not in CVs` rows |
| 5C · rewrite | a weak search is never retried | LLM writes a better query, loop back to retrieve | `paraphrase`, `exact` rows |
| 5D · understand | "Which hospital did HE…" | LLM rewrites the follow-up so it stands alone | `follow-up` rows |

Behind? `cp challenge/checkpoints/agentic_done.py challenge/agentic.py`, then Reload.
Our run on the 24 CVs, same naive pipeline underneath: see the session slides.

Then make it a tool for other agents: `challenge/mcp_live/README.md` (build an MCP server step by step)
and the skills in `.claude/skills/` and `.kiro/skills/` (`shortlist-candidates`, `screen-cv`).

## Step 7 in detail · Graph RAG

Vector search finds *similar text*. A graph stores *facts as connections*, so "which candidates know
Kubernetes?" becomes "every node connected to Kubernetes": all 9 people, no top-K limit.
You need only **networkx** (already installed). The graph is rebuilt on every Reload.

| Part | What it does | Prompt for Claude Code or Kiro |
|------|--------------|--------------------------------|
| **7a · Extract** | For each CV, find its entities: skills and the city it lists | "In challenge/pipeline.py, write extract(text) that returns the skills and the city found in one CV. Use a SKILLS list (about 80 tech words: python, kafka, kubernetes, power bi, n8n, fastapi…) and a CITIES list, matched as whole words. Look for the city only in the first 250 characters, so 'Tel Aviv University' does not count." |
| **7b · Build** | Turn the facts into a graph | "Fill in build_graph(chunks): group the chunks by source, call extract on each CV, and add edges ('candidate', name) —has_skill— ('skill', x) and —lives_in— ('city', y). Give every candidate node source=<file name>. Keep the graph in a global GRAPH and return it." Then open the 🕸 Graph tab and pick *skill: kubernetes* |
| **7c · Query** | Answer list questions from the graph | "Change retrieve: if the question asks 'which / who … candidates' and names a skill or city node of GRAPH, take every candidate connected to it (all of them, if it names two: the intersection), fetch each one's best chunk from Chroma with where={'source': ...}, and return them with via='graph: <entity> → <name>'. Otherwise use the normal search." |

**Stretch (production style):** replace the word lists with one LLM call per CV:
`llm("Return JSON: {skills: [], companies: [], city: ''}", cv_text)`. Save the result to a JSON
file so Reload does not call the LLM 24 times again. Real systems do the same with
Microsoft GraphRAG, LightRAG, LlamaIndex or LangChain's graph tools, and store the graph in Neo4j.

## The questions JSON (Verify)

```json
{"questions": [
  {"id": "q01", "type": "exact", "question": "What did Fadi Khalil build at Cedar Payments?",
   "expected": ["Fadi_Khalil"], "answer_contains": ["onboarding"]},
  {"id": "q05", "type": "follow-up", "question": "And where did he study?",
   "history": ["Who made a website much faster to load?"], "expected": ["Eitan_Barak"]},
  {"id": "q08", "type": "not in CVs", "question": "Which candidate has a pilot license?", "refuse": true}
]}
```

- `expected`: the CV file names (or a part of them) that must be retrieved. Several = all of them.
- `refuse: true`: no CV contains the answer; the bot must say it does not know.
- `history`: earlier questions in the same chat (for follow-ups).
- `answer_contains`: words the answer must contain (checked only when answers are on).

`questions_example.json` works on the practice CVs: `CV_DIR=data/cvs/candidates python challenge/app.py`.

## Rules

- **One change, then Verify.** Keep a log: step → passed, Hit@K, MRR, time.
- **No hardcoding** names or answers from the questions: the final uses questions you have not seen.
- **The CVs are real people's data.** Keep them on your laptop, out of git and out of any public place,
  and judge candidates only on job-relevant facts.
