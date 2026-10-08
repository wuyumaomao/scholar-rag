# Learning Chat SSE Design

## Goal

Show generated answers progressively in the learning frontend while preserving the existing JSON chat API for curl-based checks and other callers.

## Scope

- Keep `POST /api/chat` and its current JSON response unchanged.
- Add `POST /api/chat/stream` using Server-Sent Events (SSE).
- Change the learning frontend chat flow to use the streaming endpoint.
- Reuse the existing file validation, retrieval, grounded prompt, and session storage behavior.
- Do not add conversation-history prompting, cancellation UI, retry/resume, or streaming retrieval progress in this change.

## Backend design

The chat router will share request validation and retrieval preparation between the JSON and streaming endpoints so the two paths cannot drift in file checks, session checks, retrieval parameters, or no-evidence behavior. `AnswerGenerator` will expose an asynchronous streaming method backed by the existing LangChain prompt-model-parser chain and `astream()`.

The streaming endpoint will send UTF-8 SSE events with JSON data:

- `event: token`: one generated text fragment, with `data` containing `{"text":"..."}`.
- `event: done`: successful completion, with `data` containing `{"session_id":"..."}`.
- `event: error`: safe public error detail when generation fails after the response has started.

Errors detected before streaming starts, such as a missing file or session, remain ordinary HTTP error responses. The deterministic no-evidence answer will also be emitted through `token` events and then `done`, keeping the frontend contract uniform.

The backend will create or update the session and persist the user/assistant exchange only after generation completes successfully. A generation failure will not save a partial answer. Error logs will retain only the existing safe error category and will not include credentials, headers, or full request URLs.

## Frontend design

The frontend will continue making a POST request with JSON using `fetch`; native `EventSource` is unsuitable because it does not support a POST body. A small SSE reader will decode UTF-8 incrementally, parse complete event frames across arbitrary network chunk boundaries, append each `token` fragment to the current assistant message, and handle `done` and `error` events. Non-2xx responses before the stream begins will continue to use the API's JSON error detail.

The existing loading and error states remain in place. The conversation list will refresh after `done`, once the returned `session_id` is stored. If an in-stream error occurs, the partial text remains visible as an interrupted response, the error is shown, and the failed exchange is not added to persisted history.

## Validation

- Backend tests will cover streaming token order, deterministic no-evidence streaming, completion/session persistence, pre-stream HTTP errors, and generation failure without persisting a partial exchange.
- Frontend tests will cover SSE parsing when UTF-8 text and event frames are split across chunks, successful completion, in-stream errors, and non-2xx JSON errors.
- Run the full backend test suite, frontend tests, frontend production build, Python compile check, and `git diff --check`.
- A manual smoke test will verify the visible answer grows progressively in the browser and that completed history can be reopened.

## Compatibility and limitations

Existing JSON `/api/chat` callers remain compatible. SSE starts only after file/session validation and retrieval finish, so this change streams model output but does not stream retrieval progress. If the client disconnects, the server should stop consuming the model stream where the framework and provider permit it; no completion event or persisted exchange should be produced for an interrupted generation.
