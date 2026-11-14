/**
 * Component tests for `MarkdownRenderer`.
 *
 * The renderer is the only place where model-authored text becomes HTML, so
 * these tests assert both the *rendering* contract (headings, code blocks,
 * tables) and the *content-safety* contract (external links open safely,
 * dangerous URL schemes are neutralised).
 *
 * They cover:
 *   - REQ-016 — UI Markdown rendering
 *   - INV-019 — client-side markdown rendering and content safety
 */

import assert from "node:assert/strict";
import test, { after, before } from "node:test";

import { click, flush, renderComponent, setupClientDom } from "./helpers/clientDom.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let cleanupDom;
let React;
let MarkdownRenderer;

/**
 * Render markdown content and return the container.
 *
 * @param {string} content The markdown source.
 * @param {object} props Extra component props.
 * @returns {Promise<{container: HTMLElement, unmount: Function}>} The handle.
 */
async function renderMarkdown(content, props = {}) {
  return renderComponent(
    React.createElement(MarkdownRenderer, { content, ...props })
  );
}

before(async () => {
  cleanupDom = setupClientDom();
  React = (await import("react")).default;
  ({ MarkdownRenderer } = await loadModule("components/MarkdownRenderer.tsx"));
});

after(async () => {
  await cleanupModules();
  cleanupDom?.cleanup();
});

test("REQ-016: markdown is rendered into HTML elements in the browser", async () => {
  const { container, unmount } = await renderMarkdown(
    "# Heading\n\nSome **bold** and *italic* text."
  );

  assert.ok(container.querySelector("h1"), "expected an <h1>");
  assert.equal(container.querySelector("h1").textContent, "Heading");
  assert.ok(container.querySelector("strong"), "expected a <strong>");
  assert.ok(container.querySelector("em"), "expected an <em>");

  await unmount();
});

test("REQ-016: GFM tables are rendered inside a scroll wrapper", async () => {
  const { container, unmount } = await renderMarkdown(
    "| Name | Value |\n| --- | --- |\n| alpha | 1 |"
  );

  const wrapper = container.querySelector(".markdown-table-wrapper");
  assert.ok(wrapper, "expected a table wrapper");
  const table = wrapper.querySelector("table");
  assert.ok(table);
  assert.equal(table.querySelectorAll("th").length, 2);
  assert.equal(table.querySelectorAll("td").length, 2);
  assert.equal(table.querySelector("td").textContent, "alpha");

  await unmount();
});

test("REQ-016: fenced code blocks expose their language and a copy button", async () => {
  const { container, unmount } = await renderMarkdown(
    "```python\nprint('hello')\n```"
  );

  const block = container.querySelector(".code-block-container");
  assert.ok(block, "expected a code block container");
  assert.equal(block.querySelector(".code-block-lang").textContent, "python");
  assert.ok(block.querySelector("pre code"), "expected a <pre><code>");
  assert.match(block.querySelector("pre code").textContent, /print\('hello'\)/);

  const copyButton = block.querySelector("button.code-copy-btn");
  assert.ok(copyButton, "expected a copy button");
  assert.equal(copyButton.getAttribute("title"), "Copy code");
  assert.match(copyButton.textContent, /Copy/);

  await unmount();
});

test("REQ-016: a code block without a language is labelled 'text'", async () => {
  const { container, unmount } = await renderMarkdown("```\nplain\n```");

  assert.equal(
    container.querySelector(".code-block-lang").textContent,
    "text"
  );

  await unmount();
});

test("REQ-016: the copy button copies the code and confirms it", async (t) => {
  // The component resets the "Copied!" state on a 2s timer. Fake timers keep
  // the test fast and stop the timer from outliving the jsdom window.
  t.mock.timers.enable({ apis: ["setTimeout"] });

  const written = [];
  globalThis.navigator.clipboard = {
    writeText: async (value) => {
      written.push(value);
    },
  };

  const { container, unmount } = await renderMarkdown(
    "```python\nprint('hello')\n```"
  );

  await click(container.querySelector("button.code-copy-btn"));

  assert.deepEqual(written, ["print('hello')"]);
  assert.match(container.querySelector("button.code-copy-btn").textContent, /Copied!/);

  t.mock.timers.tick(2000);
  await flush(() => {});
  await unmount();
  t.mock.timers.reset();
});

test("INV-019: external links open in a new tab with a safe rel", async () => {
  const { container, unmount } = await renderMarkdown(
    "[docs](https://example.com/docs)"
  );

  const link = container.querySelector("a");
  assert.equal(link.getAttribute("href"), "https://example.com/docs");
  assert.equal(link.getAttribute("target"), "_blank");
  assert.equal(link.getAttribute("rel"), "noopener noreferrer");

  await unmount();
});

test("INV-019: protocol-relative links are treated as external", async () => {
  const { container, unmount } = await renderMarkdown("[cdn](//cdn.example.com/x)");

  const link = container.querySelector("a");
  assert.equal(link.getAttribute("target"), "_blank");
  assert.equal(link.getAttribute("rel"), "noopener noreferrer");

  await unmount();
});

test("INV-019: relative links stay in the current tab", async () => {
  const { container, unmount } = await renderMarkdown("[local](/agents/123)");

  const link = container.querySelector("a");
  assert.equal(link.getAttribute("href"), "/agents/123");
  assert.equal(link.getAttribute("target"), null);
  assert.equal(link.getAttribute("rel"), null);

  await unmount();
});

test("INV-019: dangerous URL schemes are neutralised", async () => {
  const { container, unmount } = await renderMarkdown(
    "[click](javascript:alert('xss'))"
  );

  const link = container.querySelector("a");
  const href = link.getAttribute("href") ?? "";
  assert.ok(
    !href.toLowerCase().startsWith("javascript:"),
    `expected the javascript: scheme to be stripped, got ${href}`
  );

  await unmount();
});

test("INV-019: raw HTML in the markdown source is not injected as markup", async () => {
  const { container, unmount } = await renderMarkdown(
    "<script>window.__pwned = true;</script>\n\n<img src=x onerror=\"window.__pwned = true\">"
  );

  assert.equal(container.querySelector("script"), null);
  assert.equal(globalThis.window.__pwned, undefined);

  await unmount();
});

test("the variant selects the user or assistant styling", async () => {
  const user = await renderMarkdown("hello", { variant: "user" });
  assert.match(user.container.querySelector(".markdown-content").getAttribute("class"), /markdown-user/);
  await user.unmount();

  const assistant = await renderMarkdown("hello", { variant: "assistant" });
  assert.match(
    assistant.container.querySelector(".markdown-content").getAttribute("class"),
    /markdown-assistant/
  );
  await assistant.unmount();
});

test("an empty content string renders an empty container without throwing", async () => {
  const { container, unmount } = await renderMarkdown("");

  assert.ok(container.querySelector(".markdown-content"));
  assert.equal(container.querySelector(".markdown-content").textContent, "");

  await unmount();
});
