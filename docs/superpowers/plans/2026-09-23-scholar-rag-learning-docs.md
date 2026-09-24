# ScholarRAG Learning Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Chinese, source-grounded learning path that reconstructs ScholarRAG from zero to the current Dockerized multi-agent RAG system.

**Architecture:** The documents are ordered by dependency: runtime and API foundations first, ingestion and retrieval next, then agent orchestration, frontend streaming, deployment/evaluation, and finally file-by-file exercises. Each chapter has a stable scope and links to the next chapter.

**Tech Stack:** Markdown, FastAPI, PostgreSQL, Docling, PyMuPDF, Milvus, LangChain, LangGraph, React, Vite, SSE, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-23-scholar-rag-learning-docs-design.md`

## Global Constraints

- Write in Chinese, keeping code identifiers and protocol names in English.
- Treat current source code as the source of truth; label planned or incomplete behavior explicitly.
- Do not modify existing backend, frontend, deployment, test, or user-authored documentation files.
- Keep public learning material under `doc/learning/` and use relative links.
- Preserve unrelated dirty-worktree changes.

---

### Task 1: Create learning navigation and roadmap

**Files:**
- Create: `doc/learning/README.md`
- Create: `doc/learning/00-roadmap-and-architecture.md`

**Interfaces:**
- Produces the canonical chapter order and milestone names used by all later documents.

- [ ] **Step 1: Write the navigation page**

  Link all chapters, explain the recommended reading loop, and distinguish learning reconstruction from historical commit order.

- [ ] **Step 2: Write the architecture chapter**

  Include the product goal, two runtime data flows, dependency graph, milestone checklist, and current implementation caveats.

- [ ] **Step 3: Validate links and identifiers**

  Verify every chapter link points to a file created by this plan and every referenced source path exists.

### Task 2: Document runtime and backend foundations

**Files:**
- Create: `doc/learning/01-environment-and-startup.md`
- Create: `doc/learning/02-backend-and-api.md`

**Interfaces:**
- Consumes: `docker-compose.yml`, `backend/Dockerfile`, `backend/config.py`, `backend/app/main.py`, `backend/app/dependencies.py`, `backend/app/store.py`, and router modules.
- Produces: A runnable mental model for service startup and HTTP request handling.

- [ ] **Step 1: Explain prerequisites and configuration**
- [ ] **Step 2: Trace Docker Compose service dependencies and backend lifespan**
- [ ] **Step 3: Trace `/api/chat`, file, session, management, and health routes**
- [ ] **Step 4: Explain PostgreSQL metadata versus LangGraph checkpoint state**
- [ ] **Step 5: Add verification commands and failure diagnosis**

### Task 3: Document PDF ingestion and indexing

**Files:**
- Create: `doc/learning/03-pdf-ingestion.md`

**Interfaces:**
- Consumes: `backend/app/routers/files.py`, `backend/rag/models.py`, `backend/rag/integration.py`, and `backend/rag/node_generator.py`.
- Produces: A step-by-step explanation from uploaded bytes to parent/child Milvus documents.

- [ ] **Step 1: Explain validation, SHA-256 deduplication, and rollback**
- [ ] **Step 2: Explain Docling parsing, cleanup, reading order, OCR fallback, and section classification**
- [ ] **Step 3: Explain `PaperNode`, generators, captions, references, and figure crops**
- [ ] **Step 4: Explain metadata, chunk IDs, parent/child chunks, and Milvus writes**
- [ ] **Step 5: Add a sample data trace and ingestion exercises**

### Task 4: Document retrieval and citation

**Files:**
- Create: `doc/learning/04-retrieval.md`

**Interfaces:**
- Consumes: `backend/rag/retrieval.py`, `backend/rag/cache.py`, `backend/rag/citation.py`, `backend/rag/factory.py`, and retrieval tests.
- Produces: A complete explanation of candidate search, fusion, reranking, expansion, filtering, caching, and citations.

- [ ] **Step 1: Explain dense/BM25 stores and RRF**
- [ ] **Step 2: Trace `Retriever.retrieve()` branch by branch**
- [ ] **Step 3: Explain Milvus filter expressions and paper scope isolation**
- [ ] **Step 4: Explain CrossEncoder, parent expansion, deduplication, and cache scope**
- [ ] **Step 5: Add parameter tuning guidance and tests to read**

### Task 5: Document LangGraph agents

**Files:**
- Create: `doc/learning/05-langgraph-agents.md`

**Interfaces:**
- Consumes: `backend/agent/states.py`, `backend/agent/graph.py`, `backend/agent/nodes.py`, `backend/agent/prompts.py`, and `backend/app/routers/chat.py`.
- Produces: A state-and-edge level explanation of the main graph, subgraph, parallel dispatch, memory, synthesis, and optional reflection.

- [ ] **Step 1: Explain state schemas and reducers**
- [ ] **Step 2: Trace the main graph and `Send` dispatch**
- [ ] **Step 3: Trace retrieve/generate/reflect/retry in the subgraph**
- [ ] **Step 4: Explain citation remapping and conversation summarization**
- [ ] **Step 5: Mark VLM injection and retry configuration gaps accurately**

### Task 6: Document React and SSE

**Files:**
- Create: `doc/learning/06-frontend-and-sse.md`

**Interfaces:**
- Consumes: `frontend/src/App.jsx`, `frontend/src/api.js`, component files, `frontend/vite.config.js`, and `frontend/nginx.conf`.
- Produces: A browser-to-backend event-flow explanation and frontend reading path.

- [ ] **Step 1: Explain component ownership and state**
- [ ] **Step 2: Explain the manual SSE parser and event contract**
- [ ] **Step 3: Trace upload, session switching, paper scope, and cancellation**
- [ ] **Step 4: Explain development proxy versus production Nginx routing**

### Task 7: Document deployment, evaluation, and exercises

**Files:**
- Create: `doc/learning/07-deployment-evaluation.md`
- Create: `doc/learning/08-reading-order-and-exercises.md`

**Interfaces:**
- Consumes: Dockerfiles, Compose, Makefile, tests, evaluation scripts, configuration templates, and existing project documentation.
- Produces: A practical verification checklist, risk register, file-by-file reading order, and staged exercises.

- [ ] **Step 1: Explain Compose startup, volumes, health checks, and external model APIs**
- [ ] **Step 2: Explain unit/integration/manual tests and retrieval/generation metrics**
- [ ] **Step 3: Explain VLM configuration versus actual injection status**
- [ ] **Step 4: Add a staged exercise ladder from fake retrieval to production hardening**

### Task 8: Final documentation QA

**Files:**
- Modify: any new `doc/learning/*.md` file only if corrections are needed.

- [ ] **Step 1: Search for stale filenames, unmarked assumptions, and placeholder text**
- [ ] **Step 2: Check all Markdown links and code paths**
- [ ] **Step 3: Compare implementation claims against source with `rg`**
- [ ] **Step 4: Run a final `git diff --check` and report validation limits**
