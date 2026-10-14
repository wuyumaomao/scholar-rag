import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { JSDOM } from "jsdom";
import { createServer } from "vite";

const originalFetch = globalThis.fetch;
const originalWindow = globalThis.window;
const originalDocument = globalThis.document;
const originalActEnvironment = globalThis.IS_REACT_ACT_ENVIRONMENT;

afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
  if (originalDocument === undefined) delete globalThis.document;
  else globalThis.document = originalDocument;
  globalThis.IS_REACT_ACT_ENVIRONMENT = originalActEnvironment;
});

test("session history loading blocks sending against the previously selected session", async () => {
  let resolveHistory;
  let streamRequestCount = 0;
  globalThis.fetch = async (url) => {
    if (url === "/api/files") {
      return Response.json([{ file_id: "file-1", filename: "paper.pdf" }]);
    }
    if (url === "/api/sessions") {
      return Response.json([
        { session_id: "session-a", title: "Session A" },
        { session_id: "session-b", title: "Session B" },
      ]);
    }
    if (url === "/api/sessions/session-b/history") {
      return new Promise((resolve) => { resolveHistory = resolve; });
    }
    if (url === "/api/chat/stream") streamRequestCount += 1;
    throw new Error(`Unexpected request: ${url}`);
  };

  const dom = new JSDOM("<div id='root'></div>", { url: "http://localhost" });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  dom.window.HTMLElement.prototype.scrollIntoView = () => {};
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const vite = await createServer({
    server: { middlewareMode: true, hmr: false, ws: false },
    appType: "custom",
  });
  const { default: App } = await vite.ssrLoadModule("/src/App.jsx");
  const container = document.getElementById("root");
  const root = createRoot(container);

  await act(async () => {
    root.render(createElement(App));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  await act(async () => {
    [...container.querySelectorAll(".session-item button")]
      .find((button) => button.textContent === "Session B")
      .click();
  });

  const textarea = container.querySelector("textarea");
  assert.equal(textarea.disabled, true);
  assert.equal(container.querySelector("button[type='submit']").disabled, true);
  Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, "value")
    .set.call(textarea, "Question while history is loading");
  textarea.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  await act(async () => {
    container.querySelector("form").dispatchEvent(
      new dom.window.Event("submit", { bubbles: true, cancelable: true }),
    );
  });
  assert.equal(streamRequestCount, 0);

  await act(async () => {
    resolveHistory(Response.json([
      { role: "user", content: "Earlier question" },
      { role: "assistant", content: "Earlier answer [S1, p. 3]", sources: [{ source_id: "S1", filename: "paper.pdf", page_nums: [3], section_path: [], text: "Saved source text" }] },
    ]));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  assert.equal(textarea.disabled, false);
  assert.equal(container.textContent.includes("Earlier answer"), true);
  await act(async () => container.querySelector(".citation-button").click());
  assert.ok(container.querySelector(".source-card").textContent.includes("Saved source text"));

  await act(async () => root.unmount());
  await vite.close();
  dom.window.close();
  assert.equal(streamRequestCount, 0);
});
