import assert from "node:assert/strict";
import { test } from "node:test";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { JSDOM } from "jsdom";
import { createServer } from "vite";

test("citations expand the correct safe source, preserve code and tolerate streaming/legacy messages", async () => {
  const previous = { window: globalThis.window, document: globalThis.document, act: globalThis.IS_REACT_ACT_ENVIRONMENT };
  const dom = new JSDOM("<div id='root'></div>", { url: "http://localhost" });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const vite = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: "custom" });
  const { default: SourceMessage } = await vite.ssrLoadModule("/src/SourceMessage.jsx");
  const container = document.getElementById("root");
  const root = createRoot(container);
  const sources = [
    { source_id: "S1", filename: "first.pdf", page_nums: [3], section_path: ["Methods"], text: '<script>alert("unsafe")</script>\nSource one' },
    { source_id: "S2", filename: "second.pdf", page_nums: [7], section_path: [], text: "Source two" },
  ];
  async function render(content, metadata = sources) {
    await act(async () => root.render(createElement(SourceMessage, { message: { content, sources: metadata } })));
  }
  try {
    await render("Partial [S1, p.");
    assert.equal(container.querySelectorAll(".citation-button").length, 0);
    await render("**Answer** [S1, p. 3]. Also [S1, S2] and unknown [S9].\n\n`[S1]`\n\n```text\n[S2]\n```\n\n[external](https://example.com)\n\n<script>alert('bad')</script>");
    assert.equal(container.querySelectorAll(".citation-button").length, 3);
    assert.equal(container.querySelectorAll("code .citation-button").length, 0);
    assert.equal(container.querySelector("script"), null);
    assert.equal(container.querySelector("a[href='https://example.com']").textContent, "external");
    assert.ok(container.textContent.includes("[S9]"));
    await act(async () => container.querySelector("[aria-label='查看来源 S1']").click());
    assert.ok(container.querySelector(".source-card").textContent.includes("first.pdf"));
    assert.ok(container.querySelector(".source-card").textContent.includes("PDF 页码：3"));
    assert.equal(container.querySelector(".source-card script"), null);
    assert.ok(container.querySelector(".source-card-text").textContent.includes("<script>"));
    await act(async () => container.querySelector("[aria-label='查看来源 S2']").click());
    assert.ok(container.querySelector(".source-card").textContent.includes("Source two"));
    assert.ok(!container.querySelector(".source-card").textContent.includes("Source one"));
    await act(async () => container.querySelector("[aria-label='关闭来源卡片']").click());
    assert.equal(container.querySelector(".source-card"), null);
    // Legacy history has no sources; its citation stays plain text.
    await act(async () => root.render(createElement(SourceMessage, { message: { content: "Old answer [S1]" } })));
    assert.equal(container.querySelectorAll(".citation-button").length, 0);
  } finally {
    await act(async () => root.unmount());
    await vite.close();
    dom.window.close();
    if (previous.window === undefined) delete globalThis.window; else globalThis.window = previous.window;
    if (previous.document === undefined) delete globalThis.document; else globalThis.document = previous.document;
    globalThis.IS_REACT_ACT_ENVIRONMENT = previous.act;
  }
});
