# DBLP Explorer

An interactive knowledge graph over the [dblp](https://dblp.org) computer
science bibliography: a KPI dashboard, a co-authorship graph explorer,
PageRank/betweenness rankings, and a RAG chatbot that only ever answers from
real, cited dblp records. See `1. DBLP Explorer Technical Proposal.md` for
the full design, and `2. Initial Slicing Task Table.md` for the real,
running log of what's built, what broke, and how it was fixed.

## Prerequisites

- Docker Desktop (with the WSL2 or Hyper-V backend on Windows)
- ~2 GB free disk for the demo scope, or ~15 GB for the full real dblp dump
  (see [Data scope](#data-scope-demo-vs-full) below)
- Optional but recommended for the chatbot: an NVIDIA GPU with Docker's
  `nvidia` runtime available (`docker info` should list `nvidia` under
  `Runtimes`). Without one, the chatbot still works, just much slower - see
  [The chatbot needs a real LLM](#the-chatbot-needs-a-real-llm-pull-it-once).

## Quickstart

```bash
cp .env.example .env
# edit .env: set DB_PASSWORD, OPENALEX_MAILTO (a real contact email for
# OpenAlex's polite pool), and leave DATA_SCOPE blank for now - see below.

docker compose up -d --build
```

This starts four services:

| Service | URL | What it is |
|---|---|---|
| `web` | http://localhost:8080 (or `$WEB_PORT`) | The React app - Dashboard, Graph, Rankings, Chat |
| `api` | http://localhost:8000 | FastAPI backend, proxied by `web` under `/api` |
| `db` | localhost:5432 | PostgreSQL 16 + pgvector, the only datastore |
| `ollama` | (internal only) | Local LLM + embedding model server |

`docker compose up` alone gives you a running, empty shell - `curl
localhost:8000/health` returns `{"status":"ok"}`, and the web app loads, but
the dashboard/graph/rankings pages have nothing to show yet. You need to
load real data next.

> **Port note:** if `web`'s port is already in use on your machine (a real
> issue hit during development - something else was already listening on
> 8080), set `WEB_PORT=<some other port>` in `.env` before starting.

## Loading real data

All of the data-loading jobs live in the `jobs` container, under its own
Compose profile so they don't start automatically:

```bash
# 1. Profile the real dblp dump first (Task 0) - downloads dblp.dtd and the
#    real monthly dblp.xml.gz into ./data/, then reports on it.
docker compose --profile jobs run --rm jobs python profile_dblp.py
cat reports/dblp_profile.md

# 2. Load it into Postgres, filtered to DATA_SCOPE (see below).
docker compose --profile jobs run --rm jobs python etl.py

# 3. Optional, can run any time after step 2, and again later to pick up
#    more coverage - real OpenAlex abstracts + citation edges.
docker compose --profile jobs run --rm jobs python enrich_openalex.py

# 4. PageRank, betweenness, Louvain communities - needed before the Graph
#    Explorer and Rankings pages have anything to show.
docker compose --profile jobs run --rm jobs python centrality.py

# 5. Paper embeddings for the chatbot's semantic search. This is the slow
#    one - see the note below - and is safe to interrupt and resume later.
docker compose --profile jobs run --rm jobs python embed.py
```

Each job is idempotent and safe to re-run. `etl.py` and `centrality.py`
fully replace their own output each run; `enrich_openalex.py` and
`embed.py` only process what's still missing, so stopping and restarting
either one later just continues where it left off.

### Data scope: demo vs. full

`DATA_SCOPE` (in `.env`) controls how much of dblp actually gets loaded.
Format: `<start_year>:<comma-separated dblp venue key prefixes>`.

- **Leave it blank and set `DEMO=1`** for a fast, real, walkable demo: `
  etl.py` then uses a fixed, evidence-based scope - 7 real database/data-
  mining venues (KDD, SIGMOD, VLDB, ICDE, WSDM, SIGIR, CIKM) since 2018,
  **20,501 real papers** (this exact count was checked against the live
  loaded data, not estimated). Small enough that `centrality.py` finishes
  in well under a minute and `embed.py` finishes in a few minutes, so the
  whole pipeline - ETL through a working chatbot - is walkable in one
  sitting.
- **Set your own `DATA_SCOPE`** for the real v1 scope this project actually
  shipped with: 38 real AI/database/data-mining venues from 2000 onward,
  **334,137 real papers** - see `reports/dblp_profile.md` and P1 in the
  task table for exactly how that list was chosen (it's evidence-based, not
  the proposal's own example scope taken verbatim). At this size,
  `centrality.py` takes about 20 minutes and `embed.py` about an hour (a
  real, measured 55 minutes for all 334,137 papers, at ~94.6 papers/sec
  sustained). `embed.py` is designed to be safely left running in the
  background and resumed later if you do interrupt it.

### The chatbot needs a real LLM (pull it once)

The `ollama` service starts with no models loaded. Pull them once:

```bash
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull qwen3:8b
```

`qwen3:8b` needs about 5-6 GB of VRAM (or RAM, CPU-only, much slower). If
your GPU has less - or you have one at all - the proposal's own fallback
(§8.5) is `qwen3.5:9b` when you have ~12 GB VRAM, or a smaller quantised
model otherwise; set `OLLAMA_MODEL` in `.env` to whatever you pull. GPU
passthrough for `ollama` is already wired into `docker-compose.yml`
(`deploy.resources.reservations.devices`) - Docker will just ignore it if no
GPU is available.

## Running the tests

```bash
# Fast unit + real-database integration tests (a few seconds):
docker compose --profile jobs run --rm jobs python -m pytest tests/ -v
docker compose exec api python -m pytest tests/ -v

# The 100-question chatbot eval (slow - hits the real live LLM, ~30s/question):
docker compose exec api python -m pytest tests/test_chat_eval.py -m eval -v
```

## Project layout

```text
db/init/            Schema, indexes, dashboard views, the read-only role
jobs/                Batch jobs: profiling, ETL, enrichment, centrality, embedding
api/app/routers/     FastAPI: dashboard, graph, metrics, chat, author
web/src/pages/       React pages: Dashboard, GraphExplorer, Rankings, Chat, Author
```

## Where to look for "why"

Every real bug found while building this - and there were a lot, from a
Git-Bash path-mangling issue to a serious entity-resolution bug that was
silently merging distinct authors, to OpenAlex's real (undocumented-in-the-
proposal) rate-limit model - is recorded with its real evidence in
`2. Initial Slicing Task Table.md`, organised by proposal slice (P0-P8).
That file is the actual source of truth for project status; this README is
just how to run it.
