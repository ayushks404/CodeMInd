# CodeMind AI(currently at PHASE 3)

> Ask anything about a GitHub codebase in plain English.  
> Get cited, confidence-scored answers with live agent reasoning.

**Current status: Phase 3 complete.** LangGraph ReAct agent is running. Full async pipeline — query → Celery worker → LangGraph agent → Redis pub/sub → WebSocket → browser — is working end to end.

---

## What it does

Connect a GitHub repo. CodeMind indexes it in the background using AST-aware chunking. Then ask questions like:

- *"How does authentication work?"*
- *"Where is the rate limiter called from?"*
- *"Walk me through the indexing pipeline."*

The agent picks the right tools, searches the codebase, reads files, finds references, and streams each step to the frontend in real time. Every answer includes the source files, function names, and line numbers it used.

---

## Architecture

**Core rule: the query endpoint never waits on the LLM.** It returns a `job_id` immediately. The LangGraph agent runs inside a Celery worker. Results reach the browser through Redis pub/sub → WebSocket service → browser.

```
React Frontend (:5173)
        │
        ├── HTTP  → Auth Service (Node.js :5000)
        │           ├── /api/auth/*       register, login, logout, JWT verify
        │           ├── /api/projects/*   create, list, delete projects
        │           └── /api/query/*      dispatch query, poll job status, history
        │
        └── WS    → WebSocket Service (Node.js :5004)
                    Subscribes to Redis pub/sub (ws:notify:*)
                    Pushes events to connected browser

Auth Service → enqueues jobs to Redis
                        │
          ┌─────────────┴──────────────────┐
          │                                │
  index_jobs queue (LOW)         query_jobs queue (HIGH)
  index_worker_1                 query_worker_1
  index_worker_2                 query_worker_2
          │                      query_worker_3
          ▼                               │
  clone repo → AST chunk                 ▼
  embed → Qdrant               LangGraph ReAct agent
                                         │
                                publish to Redis pub/sub
                                         │
                              WebSocket Service → browser
```

---

## Services

| Service | Runtime | Port | What it does |
|---|---|---|---|
| `frontend` | React + Vite | 5173 | Chat UI, project dashboard, live agent trace |
| `auth` | Node.js (Express) | 5000 | Auth + projects + query dispatch — current monolith |
| `websocket` | Node.js | 5004 | Redis pub/sub → browser WebSocket bridge |
| `agent` | Python (FastAPI) | 8000 | `/health` + `/cleanup` endpoints only |
| `query_worker_1/2/3` | Python (Celery) | — | Runs LangGraph agent on `query_jobs` queue |
| `index_worker_1/2` | Python (Celery) | — | Clones, chunks, embeds repo on `index_jobs` queue |
| `qdrant` | Qdrant v1.9.2 | 6333 | Vector store — one collection per project |
| `mongo` | MongoDB 7 | 27017 | Users, projects, job status, query history |
| `redis` | Redis 7 | 6379 | Celery broker + result backend + pub/sub + query cache |

> `services/project/` and `services/query/` are scaffolded for the Phase 6 microservice split. Currently the `auth` monolith handles everything.

---

## Celery Configuration

Redis is both broker and result backend. Tasks are routed by queue name, acked only after completion.

```
query_worker.run_query  →  query_jobs  (HIGH priority, 3 workers)
index_worker.run_index  →  index_jobs  (LOW priority,  2 workers)

task_acks_late               = True   # no ack until task finishes — no lost jobs
task_reject_on_worker_lost   = True   # requeue if worker dies mid-task
worker_prefetch_multiplier   = 4
result_expires               = 3600   # 1 hour
```

---

## The LangGraph ReAct Agent

7-node graph. State is a typed dict that flows through every node.

```
Planner → Tool Selector → Tool Executor → Observation
                                ↑               │
                                └───────────────┘  (loop if needs more info, max 3 tool calls)
                                                │
                                       Answer Generator → Critic → Memory Store → END
                                                              │
                                                              └──→ Planner  (retry if confidence < 0.8, max 3 iterations)
```

### Node breakdown

**Planner** — classifies question as `simple` or `complex` using keyword heuristics (`"how does"`, `"explain"`, `"architecture"`, `"walk me through"`, etc.). No LLM call — saves tokens.

**Tool Selector** — picks tool based on query content:

| Condition | Tool selected |
|---|---|
| First call always | `search_code` |
| File extension in query (`.py`, `.js`, `.ts`…) | `read_file` |
| "where is / called from / references / who calls" | `find_references` |
| "structure / files / directory / tree" | `get_file_tree` |
| "exact / grep / find all" | `keyword_search` |
| "signature / parameters / return type" | `get_function_signature` |
| "summarize / summary / overview of file" | `summarise_file` |
| Default | `search_code` (different query angle) |

**Tool Executor** — runs the selected tool. After every tool call, publishes an `agent_step` event to Redis pub/sub. Frontend renders these live: *"Searching codebase for..."*, *"Reading file: auth.js"*.

**Observation** — checks if tool results are non-empty. If empty and under 3 tool calls total, routes back to Tool Selector. Otherwise routes to Answer Generator.

**Answer Generator** — builds context from all tool results with token caps (Groq free tier limit):

| Content type | Cap |
|---|---|
| Per search/Qdrant chunk | 800 chars |
| Per `read_file` result | 1500 chars |
| File tree | 800 chars |
| Keyword search lines | 5 lines max |
| **Total context hard cap** | **4000 chars** |

Streams LLM response token by token via `llm.stream()`, publishing each token as an `answer_chunk` event. Parses Groq 429 rate limit errors, extracts the exact wait time from the error message, sleeps, and retries once.

**Critic** — computes confidence score as cosine similarity between the question embedding and retrieved chunk embeddings. If `confidence < 0.8` and `iterations < 3`, reruns from Planner with a refined query. Otherwise accepts.

**Memory Store** — saves the last 10 conversation turns to Redis under key `memory:{user_id}:{project_id}` with 24hr TTL. Mem0 persistent memory is stubbed here for Phase 4.

---

## Indexing Pipeline

When a project is created, the auth service fires a non-blocking request to `/index-repo` on the agent service. This enqueues a Celery `index_jobs` task.

The index worker:

1. Validates `project_id` format (MongoDB ObjectId or UUID) and GitHub URL (regex against `github.com/owner/repo`)
2. Clones the repo to `./tmp/repos/<project_id>/`
3. Walks all `.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.java`, `.cpp`, `.c`, `.md` files — skips `node_modules`, `.git`, `__pycache__`, `dist`, `build`, `.venv`
4. Chunks each file with the AST-aware chunker:
   - **Python** — uses the built-in `ast` module. Splits on `FunctionDef`, `AsyncFunctionDef`, `ClassDef` node boundaries. Each chunk is a complete function or class.
   - **JS/TS** — regex heuristic on `function`, `const`, `class` patterns. Avoids tree-sitter install overhead.
   - **Other** — falls back to 50-line overlap chunks.
   - Every chunk carries: `file`, `language`, `chunk_type`, `function_name`, `class_name`, `start_line`, `end_line`
5. Embeds all chunks with `fastembed` (`BAAI/bge-small-en-v1.5`, 384-dim, runs locally, no API cost)
6. Batch upserts to Qdrant collection `project_{project_id}` (100 points per batch). Full metadata stored as Qdrant payload.

On completion, publishes `indexing_complete` → WebSocket → frontend updates project status.

---

## Vector Store

Qdrant replaces FAISS. FAISS stored `.faiss` files that died on container restart. Qdrant persists in a Docker volume.

`QdrantIndexWrapper` and `QdrantMetadataProxy` mimic the FAISS `(index, metadata)` tuple API exactly — `rag_engine.py` required zero changes. Vectors are retrieved by cosine similarity. Metadata is fetched by point ID with a local dict cache inside `QdrantMetadataProxy`.

---

## Query Cache

Before any job is enqueued, the query controller computes:

```
SHA-256(project_id + ":" + question.trim().toLowerCase())
→ cache:query:{hash}
```

On hit — returns cached answer immediately, no Celery task, no LLM call.

On miss — stores `job:cache_key:{job_id} → cacheKey` in Redis (2hr TTL) so the worker can write the completed answer to cache.

---

## WebSocket Authentication

The WebSocket service never holds the JWT secret. On every new connection:

1. Extracts `user_id` and `token` from the WS URL query params
2. Calls `POST /api/auth/verify` on the auth service with the token
3. Auth service decodes JWT, confirms user still exists in MongoDB, returns `{ valid: true, user_id }`
4. Rejects connection if `user_id` in URL doesn't match token's `user_id` — prevents session spoofing

`useJobPoller.js` in the frontend polls `GET /api/query/:jobId` every 2 seconds as fallback if WebSocket fails to connect.

---

## Redis Events

All Python → browser communication goes through Redis pub/sub on channel `ws:notify:{user_id}`.

| Event | Fired when | Key fields |
|---|---|---|
| `agent_step` | After every tool call | `job_id`, `step`, `tool_used` |
| `answer_chunk` | Each streamed LLM token | `job_id`, `chunk` |
| `query_complete` | Agent finishes | `job_id`, `answer`, `confidence`, `sources`, `trace` |
| `indexing_complete` | Repo indexed | `project_id`, `file_count`, `chunk_count` |
| `job_failed` | Worker max retries exceeded | `job_id`, `reason`, `retryable` |

---

## Local Setup

Requires Docker and Docker Compose.

```bash
git clone https://github.com/yourusername/codemind-ai
cd codemind-ai
cp .env.example infrastructure/.env
# Fill in GROQ_API_KEY and JWT_SECRET in infrastructure/.env
cd infrastructure
docker compose up --build
```

Open `http://localhost:5173`

---

## Environment Variables

```env
# LLM
GROQ_API_KEY=gsk_your_key_here

# Auth
JWT_SECRET=long_random_string_here

# Databases
MONGO_URI=mongodb://mongo:27017/codemind
REDIS_URL=redis://redis:6379/0
QDRANT_URL=http://qdrant:6333

# Internal service URLs (Docker network)
AI_SERVICE_URL=http://agent:8000
AUTH_SERVICE_URL=http://auth:5000

# Frontend
FRONTEND_URL=http://localhost:5173
VITE_API_URL=http://localhost:5000/api

# Ports
PORT=5000
WS_PORT=5004
```

---

## Project Structure

```
codemind-fixed/
├── .env.example
├── .gitignore
├── .github/
│   └── workflows/
│
├── frontend/
│   ├── Dockerfile
│   ├── index.html
│   ├── package.json
│   ├── tailwind.config.js
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx
│       ├── api.js
│       ├── index.css
│       ├── main.jsx
│       ├── components/
│       │   ├── MessageBubble.jsx
│       │   └── Navbar.jsx
│       ├── context/
│       │   └── AuthContext.jsx
│       ├── hooks/
│       │   ├── useWebSocket.js        # primary — listens to Redis pub/sub events
│       │   └── useJobPoller.js        # fallback — polls /api/query/:jobId if WS fails
│       └── pages/
│           ├── query.jsx              # chat UI — AgentTrace, SourceList, live streaming
│           ├── dashboard.jsx          # project list + creation
│           ├── login.jsx
│           └── register.jsx
│
├── services/
│   ├── auth/                          # Node.js monolith :5000
│   │   ├── Dockerfile
│   │   ├── server.js
│   │   └── src/
│   │       ├── controllers/
│   │       │   ├── authcontrollers.js       # register, login, logout, JWT verify endpoint
│   │       │   ├── project_controllers.js   # create, list, delete + indexing trigger
│   │       │   └── query_controllers.js     # cache check, job dispatch, status poll
│   │       ├── jobs/
│   │       │   ├── query_job_producer.js    # pushes Celery-format task to query_jobs
│   │       │   └── index_job_producer.js    # pushes Celery-format task to index_jobs
│   │       ├── middleware/
│   │       │   └── authmiddleware.js
│   │       ├── models/
│   │       │   ├── user.js
│   │       │   ├── project.js
│   │       │   ├── query.js
│   │       │   └── job_status.js
│   │       └── routes/
│   │           ├── auth_routes.js
│   │           ├── project_routes.js
│   │           └── query_routes.js
│   │
│   ├── project/                       # scaffolded — Phase 6 microservice split
│   │   ├── Dockerfile
│   │   ├── server.js
│   │   └── src/
│   │       ├── controllers/
│   │       │   └── project_controllers.js
│   │       ├── jobs/
│   │       ├── middleware/
│   │       │   └── authmiddleware.js
│   │       ├── models/
│   │       │   └── project.js
│   │       ├── routes/
│   │       │   └── project_routes.js
│   │       └── webhooks/
│   │
│   ├── query/                         # scaffolded — Phase 6 microservice split
│   │   ├── Dockerfile
│   │   ├── server.js
│   │   └── src/
│   │       ├── controllers/
│   │       │   └── query_controllers.js
│   │       ├── jobs/
│   │       │   ├── query_job_producer.js
│   │       │   └── index_job_producer.js
│   │       ├── middleware/
│   │       │   └── authmiddleware.js
│   │       ├── models/
│   │       │   ├── job_status.js
│   │       │   └── query.js
│   │       ├── routes/
│   │       │   └── query_routes.js
│   │       └── websocket/
│   │
│   ├── websocket/                     # Node.js :5004
│   │   ├── Dockerfile
│   │   ├── package.json
│   │   └── src/
│   │       ├── server.js              # WS server + JWT verify via auth service
│   │       └── redis_subscriber.js    # psubscribes to ws:notify:* pattern
│   │
│   └── agent/                         # Python — all AI logic
│       ├── Dockerfile
│       ├── app.py                     # FastAPI — /health + /cleanup
│       ├── celery_app.py              # Celery init, queue routing, task config
│       ├── llm_client.py
│       ├── requirements.txt
│       ├── graph/
│       │   ├── react_graph.py         # 7-node LangGraph ReAct graph
│       │   └── critic.py              # standalone critic function (confidence < 0.5)
│       ├── tools/
│       │   ├── search_tool.py         # semantic search via Qdrant
│       │   ├── file_tools.py          # read_file, get_file_tree, keyword_search,
│       │   │                          # get_function_signature, summarise_file
│       │   └── reference_tool.py      # find_references
│       ├── rag/
│       │   ├── chunker.py             # AST-aware chunker (Python ast + JS regex + fallback)
│       │   ├── rag_engine.py          # index_repo + answer_question pipeline
│       │   ├── embeddings.py          # fastembed BAAI/bge-small-en-v1.5 wrapper
│       │   ├── vector_store.py        # Qdrant client + FAISS-compatible wrapper API
│       │   └── repo_cloner.py
│       ├── workers/
│       │   ├── query_worker.py        # Celery task — runs LangGraph graph
│       │   └── index_worker.py        # Celery task — clone, chunk, embed, upsert
│       ├── notifications/
│       │   └── redis_publisher.py     # publish_agent_step, answer_chunk, query_complete,
│       │                              # indexing_complete, job_failed
│       ├── memory/                    # placeholder — Mem0 integration (Phase 4)
│       └── crews/                     # placeholder — CrewAI PR analyser (Phase 5)
│
├── gateway/                           # placeholder — Nginx config (Phase 6)
├── observability/
│   └── grafana/                       # placeholder — dashboards (Phase 7)
└── infrastructure/
    ├── docker-compose.yml
    └── .env.example
```

---

## What's next

| Phase | Description | Status |
|---|---|---|
| Phase 4 | Mem0 persistent user memory — stub in `memory_store_node` gets filled | Planned |
| Phase 5 | CrewAI PR analyser — 4-agent crew, structured risk report, GitHub webhook | Planned |
| Phase 6 | Proper microservice split — `services/project/` and `services/query/` go live | Planned |
| Phase 7 | Observability — structured logging, Sentry, Prometheus, Grafana dashboards | Planned |
| Phase 8 | Onboarding agent, codebase map, CI/CD pipeline | Planned |

---

## License

MIT
