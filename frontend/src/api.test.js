import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

const originalFetch = globalThis.fetch;
const encoder = new TextEncoder();

afterEach(() => {
  globalThis.fetch = originalFetch;
});

test("uploadFile sends a single PDF as the learning API's file field", async () => {
  const { uploadFile } = await import("./api.js").catch(() => ({}));
  assert.equal(typeof uploadFile, "function");

  const pdf = new File(["pdf bytes"], "paper.pdf", {
    type: "application/pdf",
  });
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return Response.json({ file_id: "file-1", filename: "paper.pdf" }, {
      status: 201,
    });
  };

  const result = await uploadFile(pdf);

  assert.equal(request.url, "/api/files/upload");
  assert.equal(request.options.method, "POST");
  assert.equal(request.options.body.get("file").name, "paper.pdf");
  assert.equal(request.options.body.has("files"), false);
  assert.equal(result.file_id, "file-1");
});

test("sendChat posts the learning API's file, query, and optional session id", async () => {
  const { sendChat } = await import("./api.js").catch(() => ({}));
  assert.equal(typeof sendChat, "function");

  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return Response.json({ answer: "Grounded answer.", session_id: "session-1" });
  };

  const result = await sendChat({
    file_id: "file-1",
    query: "How does the method work?",
    session_id: "session-1",
  });

  assert.equal(request.url, "/api/chat");
  assert.equal(request.options.method, "POST");
  assert.equal(request.options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(request.options.body), {
    file_id: "file-1",
    query: "How does the method work?",
    session_id: "session-1",
  });
  assert.equal(result.answer, "Grounded answer.");
});

test("deleteSession handles the backend's empty 204 response", async () => {
  const { deleteSession } = await import("./api.js").catch(() => ({}));
  assert.equal(typeof deleteSession, "function");

  let requestUrl;
  globalThis.fetch = async (url, options) => {
    requestUrl = `${url} ${options.method}`;
    return new Response(null, { status: 204 });
  };

  const result = await deleteSession("session-1");

  assert.equal(requestUrl, "/api/sessions/session-1 DELETE");
  assert.equal(result, null);
});

test("API errors expose the backend detail message", async () => {
  const { getFiles } = await import("./api.js").catch(() => ({}));
  assert.equal(typeof getFiles, "function");

  globalThis.fetch = async () => Response.json(
    { detail: "文件不存在" },
    { status: 404 },
  );

  await assert.rejects(getFiles(), /文件不存在/);
});

function responseFromByteChunks(chunks, status = 200) {
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
  return new Response(body, {
    status,
    headers: { "Content-Type": "text/event-stream; charset=utf-8" },
  });
}

test("streamChat posts JSON and delivers token events in order", async () => {
  const { streamChat } = await import("./api.js");
  const bytes = encoder.encode(
    'event: token\ndata: {"text":"The method "}\n\nevent: token\ndata: {"text":"works."}\n\nevent: done\ndata: {"session_id":"session-1"}\n\n',
  );
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return responseFromByteChunks([
      bytes.slice(0, 19),
      bytes.slice(19, 61),
      bytes.slice(61),
    ]);
  };
  const tokens = [];

  const result = await streamChat({
    file_id: "file-1",
    query: "How does it work?",
    session_id: "session-1",
    onToken: (text) => tokens.push(text),
  });

  assert.equal(request.url, "/api/chat/stream");
  assert.equal(request.options.method, "POST");
  assert.equal(request.options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(request.options.body), {
    file_id: "file-1",
    query: "How does it work?",
    session_id: "session-1",
  });
  assert.deepEqual(tokens, ["The method ", "works."]);
  assert.deepEqual(result, { session_id: "session-1" });
});

test("streamChat preserves UTF-8 characters split across network chunks", async () => {
  const { streamChat } = await import("./api.js");
  const bytes = encoder.encode(
    'event: token\ndata: {"text":"中文回答"}\n\nevent: done\ndata: {"session_id":"session-1"}\n\n',
  );
  const firstChineseByte = bytes.indexOf(0xe4);
  globalThis.fetch = async () => responseFromByteChunks([
    bytes.slice(0, firstChineseByte + 1),
    bytes.slice(firstChineseByte + 1),
  ]);
  const tokens = [];

  const result = await streamChat({
    file_id: "file-1",
    query: "Question?",
    onToken: (text) => tokens.push(text),
  });

  assert.deepEqual(tokens, ["中文回答"]);
  assert.equal(result.session_id, "session-1");
});

test("streamChat exposes safe SSE errors after preserving prior tokens", async () => {
  const { streamChat } = await import("./api.js");
  globalThis.fetch = async () => responseFromByteChunks([
    encoder.encode(
      'event: token\ndata: {"text":"partial"}\n\nevent: error\ndata: {"detail":"回答生成服务当前不可用"}\n\n',
    ),
  ]);
  const tokens = [];

  await assert.rejects(
    streamChat({
      file_id: "file-1",
      query: "Question?",
      onToken: (text) => tokens.push(text),
    }),
    /回答生成服务当前不可用/,
  );
  assert.deepEqual(tokens, ["partial"]);
});

test("streamChat parses HTTP JSON errors before the SSE response starts", async () => {
  const { streamChat } = await import("./api.js");
  globalThis.fetch = async () => Response.json(
    { detail: "文件不存在" },
    { status: 404 },
  );

  await assert.rejects(
    streamChat({ file_id: "missing", query: "Question?" }),
    /文件不存在/,
  );
});

test("streamChat rejects a connection that closes before the done event", async () => {
  const { streamChat } = await import("./api.js");
  globalThis.fetch = async () => responseFromByteChunks([
    encoder.encode('event: token\ndata: {"text":"partial"}\n\n'),
  ]);

  await assert.rejects(
    streamChat({ file_id: "file-1", query: "Question?" }),
    /流式回答提前结束/,
  );
});

test("streamChat ignores unknown events and SSE comments", async () => {
  const { streamChat } = await import("./api.js");
  globalThis.fetch = async () => responseFromByteChunks([
    encoder.encode(
      ': heartbeat\n\nevent: diagnostic\ndata: plain text\n\nevent: done\ndata: {"session_id":"session-1"}\n\n',
    ),
  ]);

  const result = await streamChat({ file_id: "file-1", query: "Question?" });
  assert.equal(result.session_id, "session-1");
});

test("streamChat rejects a truncated terminal event without its frame delimiter", async () => {
  const { streamChat } = await import("./api.js");
  globalThis.fetch = async () => responseFromByteChunks([
    encoder.encode(
      'event: done\ndata: {"session_id":"session-1"}',
    ),
  ]);

  await assert.rejects(
    streamChat({ file_id: "file-1", query: "Question?" }),
    /流式回答提前结束/,
  );
});
