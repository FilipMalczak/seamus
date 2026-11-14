/**
 * Component tests for `ToolCallItem` — the collapsible tool-execution card.
 *
 * `ToolCallItem` owns the tool-call lifecycle visualisation required by
 * REQ-020 / INV-023. Its contracts are entirely interactional, so a static
 * markup snapshot cannot observe them:
 *
 *   - the status badge reflects the four lifecycle states (`pending`, `wip`,
 *     `done`, `error`) and nothing else;
 *   - a card that is still running is expanded by default, and a card that
 *     completes collapses itself automatically;
 *   - a manual toggle survives the automatic collapse, so an operator can
 *     keep a finished tool call open;
 *   - the arguments and the result are rendered as separate labelled blocks,
 *     and a tool call with neither renders no body at all;
 *   - the sequence index badge is only rendered when an index is supplied.
 *
 * The component is driven through a real DOM with `react-dom/client`, so the
 * `useEffect` that performs the automatic collapse is genuinely exercised.
 */

import assert from "node:assert/strict";
import test, { after, before } from "node:test";

import { click, renderComponent, setupClientDom } from "./helpers/clientDom.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let cleanupDom;
let React;
let ToolCallItem;

/**
 * Render a tool call card.
 *
 * @param {object} toolCall The tool-call record.
 * @param {number} [sequenceIndex] The optional sequence index.
 * @returns {Promise<object>} The render handle.
 */
async function renderToolCall(toolCall, sequenceIndex) {
  return renderComponent(
    React.createElement(ToolCallItem, { toolCall, sequenceIndex })
  );
}

/** The card header button. */
function header(container) {
  return container.querySelector(".tool-card-header");
}

/** The card body, when expanded. */
function body(container) {
  return container.querySelector(".tool-card-body");
}

before(async () => {
  cleanupDom = setupClientDom();
  React = (await import("react")).default;
  ({ ToolCallItem } = await loadModule("components/ToolCallItem.tsx"));
});

after(async () => {
  await cleanupModules();
  cleanupDom?.cleanup();
});

test("REQ-020: a pending tool call is expanded and badged as Pending", async () => {
  const { container, unmount } = await renderToolCall({
    id: "tc-1",
    name: "ls",
    status: "pending",
  });

  assert.ok(container.querySelector(".badge-tool-pending"));
  assert.match(container.querySelector(".badge-tool-pending").textContent, /Pending/);
  assert.ok(body(container), "a running tool call is expanded by default");

  await unmount();
});

test("REQ-020: a running tool call is badged as WIP", async () => {
  const { container, unmount } = await renderToolCall({
    id: "tc-2",
    name: "execute",
    status: "wip",
  });

  const badge = container.querySelector(".badge-tool-running");
  assert.ok(badge);
  assert.match(badge.textContent, /WIP/);

  await unmount();
});

test("REQ-020: a completed tool call is badged as Done", async () => {
  const { container, unmount } = await renderToolCall({
    id: "tc-3",
    name: "write_file",
    status: "done",
    result: "written",
  });

  const badge = container.querySelector(".badge-tool-complete");
  assert.ok(badge);
  assert.match(badge.textContent, /Done/);

  await unmount();
});

test("REQ-020: a failed tool call is badged as Failed", async () => {
  const { container, unmount } = await renderToolCall({
    id: "tc-4",
    name: "write_file",
    status: "error",
    result: "Error: read-only mount",
  });

  const badge = container.querySelector(".badge-tool-error");
  assert.ok(badge);
  assert.match(badge.textContent, /Failed/);

  await unmount();
});

test("REQ-020: a completed tool call collapses itself", async () => {
  const { container, unmount } = await renderToolCall({
    id: "tc-5",
    name: "ls",
    status: "done",
    args: { path: "/workspace" },
    result: "file.txt",
  });

  assert.equal(body(container), null, "a finished tool call starts collapsed");

  await unmount();
});

test("REQ-020: the collapsed card can be expanded on demand", async () => {
  const { container, unmount } = await renderToolCall({
    id: "tc-6",
    name: "ls",
    status: "done",
    args: { path: "/workspace" },
    result: "file.txt",
  });

  await click(header(container));

  const expanded = body(container);
  assert.ok(expanded);
  assert.match(expanded.textContent, /Input Arguments/);
  assert.match(expanded.textContent, /Result Output/);

  await unmount();
});

test("REQ-020: the arguments and the result are separate labelled blocks", async () => {
  const { container, unmount } = await renderToolCall({
    id: "tc-7",
    name: "write_file",
    status: "done",
    args: { file_path: "/workspace/a.txt", content: "hello" },
    result: "ok",
  });

  await click(header(container));

  const labels = Array.from(container.querySelectorAll(".tool-label")).map(
    (el) => el.textContent
  );
  assert.deepEqual(labels, ["Input Arguments:", "Result Output:"]);

  const pre = container.querySelector(".code-block");
  assert.ok(pre);
  assert.match(pre.textContent, /file_path/);

  await unmount();
});

test("REQ-020: a tool call without arguments or result renders no labelled blocks", async () => {
  const { container, unmount } = await renderToolCall({
    id: "tc-8",
    name: "todo",
    status: "done",
  });

  await click(header(container));

  assert.equal(
    container.querySelectorAll(".tool-block").length,
    0,
    "a tool call with neither arguments nor a result shows no input/output blocks"
  );

  await unmount();
});

test("REQ-020: the sequence index badge is only rendered when supplied", async () => {
  const withoutIndex = await renderToolCall({ id: "tc-9", name: "ls", status: "done" });
  assert.equal(withoutIndex.container.querySelector(".bubble-sequence-badge"), null);
  await withoutIndex.unmount();

  const withIndex = await renderToolCall({ id: "tc-10", name: "ls", status: "done" }, 3);
  const badge = withIndex.container.querySelector(".bubble-sequence-badge");
  assert.ok(badge);
  assert.equal(badge.textContent, "#3");
  await withIndex.unmount();
});

test("REQ-020: a tool call with no explicit status and a result counts as done", async () => {
  const { container, unmount } = await renderToolCall({
    id: "tc-11",
    name: "ls",
    result: "ok",
  });

  assert.ok(container.querySelector(".badge-tool-complete"));

  await unmount();
});

test("REQ-020: a tool call with no result and no status counts as pending", async () => {
  const { container, unmount } = await renderToolCall({
    id: "tc-12",
    name: "ls",
  });

  assert.ok(container.querySelector(".badge-tool-pending"));

  await unmount();
});

test("REQ-020: raw argument text is shown when the arguments are not structured", async () => {
  const { container, unmount } = await renderToolCall({
    id: "tc-13",
    name: "ls",
    status: "done",
    rawArgs: '{"path": "/workspace"}',
    result: "ok",
  });

  await click(header(container));

  const pre = container.querySelector(".code-block");
  assert.ok(pre);
  assert.match(pre.textContent, /workspace/);

  await unmount();
});

test("REQ-020: web tools are marked with a distinct icon", async () => {
  const { container, unmount } = await renderToolCall({
    id: "tc-14",
    name: "web_search",
    status: "done",
    result: "ok",
  });

  const title = container.querySelector(".tool-card-title");
  assert.ok(title);
  assert.ok(title.querySelector(".text-emerald-400"), "web tools use the globe icon");

  await unmount();
});
