# Learning Chat SSE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream generated learning-version chat answers into the browser while keeping the existing JSON `/api/chat` contract intact.

**Architecture:** Factor the existing chat validation/retrieval/persistence flow so both JSON and streaming endpoints use the same inputs and rules. Add an async `AnswerGenerator.astream()` method over the current LangChain chain, expose it through a POST SSE route, and have the React API layer parse SSE frames from `fetch` and append token events to a stable assistant message.

**Tech Stack:** FastAPI `StreamingResponse`, LangChain `Runnable.astream()` and `StrOutputParser`, browser Fetch `ReadableStream`/`TextDecoder`, React state, pytest/TestClient, Node built-in test runner, Vite.

**Spec:** `docs/superpowers/specs/2026-10-08-learning-chat-sse-design.md`

## Global Constraints

- Preserve `POST /api/chat` and its JSON `{answer, session_id}` response.
- Add `POST /api/chat/stream` with `text/event-stream` and JSON `data` for `token`, `done`, and `error` events.
- Use POST `fetch` for SSE because chat requires a JSON body; do not use native `EventSource`.
- Keep file/session validation and retrieval errors as normal HTTP errors before the streaming response begins.
- Stream the deterministic no-evidence answer with the same token/done event contract.
- Persist the user/assistant exchange only after generation succeeds; never persist a partial answer after a stream failure.
- Keep public errors safe and do not log credentials, request headers, or full endpoint URLs.
- Do not add history prompting, retry/resume, a cancel UI, or retrieval-progress events.

---

### Task 1: Add LangChain answer streaming

**Files:**
- Modify: `learning-implementation/backend/app/generation/answer_generator.py`
- Test: `learning-implementation/backend/tests/test_answer_generator.py`

**Interfaces:**
- Consumes: existing `Settings`, `RetrievalHit`, evidence formatting, and LangChain chain.
- Produces: `async def astream(self, query: str, hits: Sequence[RetrievalHit]) -> AsyncIterator[str]`.

- [x] **Step 1: Add a failing test for ordered streamed text**

In `test_answer_generator.py`, add an async test using a fake runnable whose `astream()` emits two text chunks. Consume `generator.astream(...)` with an async comprehension and assert the exact list `['The method ', 'uses a CNN-CRF.']`. Also capture the prompt and assert it contains the question and the same evidence metadata used by `generate()`.

- [x] **Step 2: Run the focused test and verify it fails**

Run from `learning-implementation/backend`:

```cmd
..\.venv\Scripts\python.exe -m pytest tests\test_answer_generator.py -k stream -q
```

Expected: FAIL because `AnswerGenerator.astream` does not exist yet.

- [x] **Step 3: Share input validation and evidence preparation**

Extract the existing query/config validation and evidence serialization into private helpers in `answer_generator.py`. Keep `generate()` behavior and its `str` return contract unchanged; have both `generate()` and `astream()` use the same prepared `{"question": ..., "evidence": ...}` input.

- [x] **Step 4: Implement asynchronous chain streaming**

Implement `AnswerGenerator.astream()` as an async generator over `self._get_chain().astream(input)`. Yield non-empty string chunks in order. Wrap provider/chain exceptions in `AnswerGenerationError` using the same safe status-only message policy as `generate()`. Track whether any non-whitespace text was emitted and raise `AnswerGenerationError("LLM returned an empty answer")` if the stream completes without usable text.

- [x] **Step 5: Test validation, no-evidence prompt, empty output, and provider failure**

Add focused tests proving blank query and disabled/incomplete LLM settings fail before the model is invoked; an empty stream raises the existing safe empty-answer error; a provider exception is wrapped without exposing its secret or URL; and an empty `hits` list includes `No relevant evidence was retrieved.` in the prompt.

- [x] **Step 6: Run generation tests**

Run:

```cmd
..\.venv\Scripts\python.exe -m pytest tests\test_answer_generator.py -q
```

Expected: all existing synchronous tests and new streaming tests pass.

### Task 2: Add the SSE chat route while preserving JSON chat

**Files:**
- Modify: `learning-implementation/backend/app/routers/chat.py`
- Test: `learning-implementation/backend/tests/test_chat.py`

**Interfaces:**
- Consumes: `AnswerGenerator.astream(query, hits)`, existing store functions, and `ChatRequest`.
- Produces: existing `POST /api/chat` unchanged; new `POST /api/chat/stream` returning SSE events:
  - `token`: `{"text": "..."}`
  - `done`: `{"session_id": "..."}`
  - `error`: `{"detail": "回答生成服务当前不可用"}` or another safe public storage-failure detail.

- [x] **Step 1: Add an SSE success test that currently fails**

In `test_chat.py`, add a test with the same temporary PDF/retrieval fakes as the JSON route test. Inject an async fake answer generator yielding `"The method "` then `"uses a CNN-CRF."`; POST to `/api/chat/stream`; assert status 200, `content-type` begins `text/event-stream`, events preserve token order, the final `done` event carries `session-1`, and stored messages contain the exact concatenated assistant answer.

- [x] **Step 2: Run the new route test and verify it fails**

Run from `learning-implementation/backend`:

```cmd
..\.venv\Scripts\python.exe -m pytest tests\test_chat.py -k stream -q
```

Expected: FAIL because `/api/chat/stream` is not registered.

- [x] **Step 3: Extract shared chat preparation and persistence helpers**

Refactor `chat.py` into private async helpers that (a) verify the file and PDF, verify an optional existing session, and retrieve hits with the current settings, and (b) create/touch the session and persist user/assistant messages. Keep error status/detail behavior and the current JSON response exactly as-is. Keep synchronous retrieval/store calls dispatched through `asyncio.to_thread`.

- [x] **Step 4: Add SSE event serialization and streaming endpoint**

Use FastAPI `StreamingResponse` with media type `text/event-stream`, `Cache-Control: no-cache`, and `X-Accel-Buffering: no`. Serialize each event as `event: <name>\ndata: <JSON>\n\n` with `json.dumps(..., ensure_ascii=False)`.

Run file/session validation and retrieval before returning `StreamingResponse`, so those errors remain normal HTTP responses. In the response generator, stream `AnswerGenerator.astream()` text as `token` events; for no hits, emit the deterministic refusal as a token. Accumulate emitted text for persistence. After successful generation, persist the completed exchange and emit `done` with the resulting session ID. On `AnswerGenerationError`, log only its sanitized message, send a safe `error` event, and do not persist. On persistence failure, send a generic safe error event and do not emit `done`; keep the current store function behavior and do not claim it provides a multi-message transaction.

- [x] **Step 5: Add failure and compatibility coverage**

Test that missing files/sessions return their current HTTP status and JSON detail before SSE begins; a no-hit request emits the deterministic answer followed by `done`; a generator exception emits `error` after any already emitted token and persists no session/messages; and the existing JSON chat test still returns exactly its current JSON shape and persists exactly two messages.

- [x] **Step 6: Run chat and session route tests**

Run:

```cmd
..\.venv\Scripts\python.exe -m pytest tests\test_chat.py tests\test_sessions.py -q
```

Expected: all JSON, SSE, and existing session lifecycle tests pass.

### Task 3: Implement and test the frontend SSE reader

**Files:**
- Modify: `learning-implementation/frontend/src/api.js`
- Test: `learning-implementation/frontend/src/api.test.js`

**Interfaces:**
- Consumes: `POST /api/chat/stream` and the event contract from Task 2.
- Produces: `streamChat({file_id, query, session_id, onToken}) -> Promise<{session_id: string}>`; `onToken(text)` is called once per decoded token event.

- [x] **Step 1: Add failing `streamChat` tests**

Use mocked `fetch` responses whose `ReadableStream` enqueues byte chunks separately. Verify request URL/method/JSON headers/body, tokens arrive in order, and the promise resolves with the `done.session_id`.

- [x] **Step 2: Test boundary and error cases**

Split a Chinese UTF-8 character across byte chunks and split SSE fields/event delimiters across chunks; assert the decoded token is intact. Verify an `error` event rejects with its safe `detail`, a non-2xx JSON response rejects with FastAPI `detail`, and a stream closing without `done` rejects as an interrupted response.

- [x] **Step 3: Run the focused Node tests and verify they fail**

Run from `learning-implementation/frontend`:

```cmd
npm test -- --test-name-pattern=streamChat
```

Expected: FAIL because `streamChat` does not exist yet.

- [x] **Step 4: Implement the POST fetch and incremental SSE parser**

Add `streamChat()` without changing `sendChat()`. Check `response.ok` before reading the body and parse JSON error details for non-2xx responses. Read with `response.body.getReader()` and `TextDecoder("utf-8")` using `{stream: true}`. Buffer text until complete blank-line-delimited SSE frames are available; parse `event` and one or more `data` fields, ignore comments/unknown events, call `onToken` for token events, save the session ID from done, and throw on error or stream EOF before done. Flush the decoder at EOF and process a final complete frame.

- [x] **Step 5: Run frontend API tests**

Run:

```cmd
npm test
```

Expected: existing upload/JSON chat/delete/error tests and new stream tests all pass.

### Task 4: Stream tokens into React and document the learning point

**Files:**
- Modify: `learning-implementation/frontend/src/App.jsx`
- Modify: `learning-implementation/rag学习文档.md`
- Validate: `learning-implementation/frontend` Vite build and browser smoke test

**Interfaces:**
- Consumes: `streamChat()` with `onToken(text)` and final `{session_id}` from Task 3.
- Produces: a visible assistant message that grows token-by-token, completed session history refresh, and a learning note explaining SSE versus JSON and why POST `fetch` is used.

- [x] **Step 1: Create stable temporary assistant message state**

When sending a question, append the user message and an empty assistant message with a unique temporary `id` in one state update. Disable another send while streaming as today. Update the assistant message by its temporary `id` in `onToken`; do not assume it remains the last list item if the user switches views while a request is running.

- [x] **Step 2: Connect the form to `streamChat()`**

Replace the `sendChat()` call in `handleSend()` with `streamChat()`. On every token, append text to the matching assistant message. On successful resolution, store the returned session ID and refresh sessions. On failure, keep any partial text visible and show the error; remove the empty temporary assistant message if no token arrived. Always clear loading in `finally`.

- [x] **Step 3: Add a concise SSE learning note**

Add the next numbered section to `learning-implementation/rag学习文档.md`: define SSE as server-to-client text events over one HTTP response; show `token`, `done`, and `error`; explain that chat still uses POST JSON with `fetch` because native `EventSource` cannot send the request body; contrast it with the preserved JSON `/api/chat` path.

- [x] **Step 4: Run frontend tests and build**

Run from `learning-implementation/frontend`:

```cmd
npm test
npm run build
```

Expected: all Node tests pass and Vite creates a successful production build.

- [x] **Step 5: Verify the full flow in the browser**

With the backend and Vite running, ask a question about an indexed paper. Confirm assistant text appears before the request finishes, the completed session is added to history, and reopening that session loads the full persisted answer. Then verify the JSON route remains available with the existing curl request shape.

### Task 5: Run complete backend validation

**Files:**
- Validate only; no additional source files.

- [x] **Step 1: Run the complete backend test suite**

Run from `learning-implementation/backend`:

```cmd
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m compileall -q app scripts
```

Expected: the entire backend suite passes and application/scripts compile.

- [x] **Step 2: Check patch whitespace and inspect final diff**

Run from repository root:

```cmd
git diff --check
git status --short
```

Expected: no whitespace errors; review only SSE implementation changes alongside the pre-existing user modifications, which must remain untouched.
