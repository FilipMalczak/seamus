/**
 * Component tests for `TerminalView` — the interactive sandbox shell.
 *
 * `TerminalView` implements REQ-037 and INV-046: the operator gets a live
 * shell attached to the session's sandbox. Its contracts are:
 *
 *   - a command is dispatched to the backend and its output streams into the
 *     terminal buffer as `stdout` / `stderr` lines;
 *   - the exit code is reported, and a non-zero exit code is visibly
 *     distinguished from a successful one;
 *   - the working directory follows the backend's reported directory across
 *     commands;
 *   - the command history is navigable with the arrow keys;
 *   - a running command can be interrupted, and the buffer can be cleared.
 *
 * The component is driven against a stubbed `fetch` that serves a scripted
 * SSE terminal stream, so the real `streamTerminalCommand` client code and
 * the real event reduction run against it. No container and no inference are
 * involved.
 */

import assert from "node:assert/strict";
import test, { after, before, beforeEach } from "node:test";

import {
  click,
  pressKey,
  renderComponent,
  setupClientDom,
  type,
} from "./helpers/clientDom.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let cleanupDom;
let React;
let TerminalView;
let sessionTerminalCache;

/**
 * The most recently rendered handle.
 *
 * The terminal view keeps a polling interval alive while it is mounted, so a
 * failing assertion must not leave a component mounted. The `afterEach`
 * hook unmounts whatever is still around.
 *
 * @type {{unmount: Function} | null}
 */
let activeHandle = null;

const AGENT_ID = "11111111-1111-4111-8111-111111111111";
const SESSION_ID = "22222222-2222-4222-8222-222222222222";

/**
 * Install a `fetch` stub serving the terminal info and stream endpoints.
 *
 * @param {object} options Stub options.
 * @returns {{requests: Array<object>}} The recorded requests.
 */
function installFetchStub(options = {}) {
  const requests = [];
  globalThis.fetch = async (url, init) => {
    const href = String(url);
    requests.push({ url: href, method: init?.method ?? "GET" });

    if (href.includes("/terminal/info")) {
      return new Response(
        JSON.stringify({
          agent_id: AGENT_ID,
          session_id: SESSION_ID,
          operational_dir: options.operationalDir ?? "/workspace",
          status: "active",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }

    if (href.includes("/terminal/stream")) {
      const events = options.events ?? [
        { type: "stdout", data: "hello from the sandbox\n" },
        { type: "exit", exit_code: 0, working_directory: "/workspace" },
      ];
      const encoder = new TextEncoder();
      const body = new ReadableStream({
        start(controller) {
          for (const event of events) {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
          }
          controller.close();
        },
      });
      return new Response(body, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    }

    return new Response("{}", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  return { requests };
}

/**
 * Render the terminal view.
 *
 * @param {object} options Render options.
 * @returns {Promise<object>} The render handle.
 */
async function renderTerminal(options = {}) {
  const stub = installFetchStub(options);
  const handle = await renderComponent(
    React.createElement(TerminalView, {
      agentId: AGENT_ID,
      sessionId: "sessionId" in options ? options.sessionId : SESSION_ID,
      sessionName: options.sessionName ?? "refactor",
      isActive: options.isActive ?? true,
    })
  );
  activeHandle = handle;
  return { ...handle, ...stub };
}

/** The command input. */
function input(container) {
  return container.querySelector(".terminal-input-field");
}

/** Flush pending promise-driven updates. */
async function settle(ms = 40) {
  const { act } = await import("react");
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms));
  });
}

before(async () => {
  cleanupDom = setupClientDom();
  React = (await import("react")).default;
  const mod = await loadModule("components/TerminalView.tsx");
  TerminalView = mod.TerminalView;
  sessionTerminalCache = mod.sessionTerminalCache;
});

after(async () => {
  await cleanupModules();
  cleanupDom?.cleanup();
});

beforeEach(() => {
  sessionTerminalCache?.clear();
});

test.afterEach(async () => {
  if (activeHandle) {
    await activeHandle.unmount();
    activeHandle = null;
  }
});

test("REQ-037: without a session the terminal renders its empty state", async () => {
  const { container, unmount } = await renderTerminal({ sessionId: null });

  assert.ok(container.querySelector(".terminal-empty-state"));
  assert.match(container.textContent, /No Session Selected/);

  await unmount();
});

test("REQ-037: the terminal asks the backend for the operational directory", async () => {
  const { requests, unmount } = await renderTerminal();
  await settle();

  assert.ok(
    requests.some((request) => request.url.includes("/terminal/info")),
    "expected a terminal info request"
  );

  await unmount();
});

test("REQ-037: the working directory is shown in the header", async () => {
  const { container, unmount } = await renderTerminal({
    operationalDir: "/workspace",
  });
  await settle();

  const badge = container.querySelector(".terminal-cwd-badge");
  assert.ok(badge);
  assert.equal(badge.textContent, "/workspace");

  await unmount();
});

test("REQ-037: a command is dispatched to the terminal stream endpoint", async () => {
  const { container, requests, unmount } = await renderTerminal();
  await settle();

  await type(input(container), "ls -la");
  await pressKey(input(container), "Enter");
  await settle();

  const post = requests.find((request) => request.url.includes("/terminal/stream"));
  assert.ok(post, "expected a terminal stream request");
  assert.equal(post.method, "POST");

  await unmount();
});

test("REQ-037: the streamed stdout is rendered in the terminal buffer", async () => {
  const { container, unmount } = await renderTerminal({
    events: [
      { type: "stdout", data: "hello from the sandbox\n" },
      { type: "exit", exit_code: 0, working_directory: "/workspace" },
    ],
  });
  await settle();

  await type(input(container), "echo hello");
  await pressKey(input(container), "Enter");
  await settle();

  assert.match(container.querySelector(".terminal-output-block").textContent, /hello from the sandbox/);

  await unmount();
});

test("REQ-037: the stderr stream is rendered distinctly", async () => {
  const { container, unmount } = await renderTerminal({
    events: [
      { type: "stderr", data: "permission denied\n" },
      { type: "exit", exit_code: 1, working_directory: "/workspace" },
    ],
  });
  await settle();

  await type(input(container), "cat /etc/shadow");
  await pressKey(input(container), "Enter");
  await settle();

  const line = container.querySelector(".terminal-output-line");
  assert.ok(line);
  assert.match(line.className, /terminal-stderr/);

  await unmount();
});

test("REQ-037: a successful exit code is reported", async () => {
  const { container, unmount } = await renderTerminal({
    events: [{ type: "exit", exit_code: 0, working_directory: "/workspace" }],
  });
  await settle();

  await type(input(container), "true");
  await pressKey(input(container), "Enter");
  await settle();

  const badge = container.querySelector(".terminal-exit-badge");
  assert.ok(badge);
  assert.match(badge.className, /success/);
  assert.equal(badge.textContent, "0");

  await unmount();
});

test("REQ-037: a failing exit code is reported as a failure", async () => {
  const { container, unmount } = await renderTerminal({
    events: [{ type: "exit", exit_code: 2, working_directory: "/workspace" }],
  });
  await settle();

  await type(input(container), "false");
  await pressKey(input(container), "Enter");
  await settle();

  const badge = container.querySelector(".terminal-exit-badge");
  assert.ok(badge);
  assert.match(badge.className, /failure/);
  assert.equal(badge.textContent, "2");

  await unmount();
});

test("INV-046: the working directory follows the backend across commands", async () => {
  const { container, unmount } = await renderTerminal({
    events: [{ type: "exit", exit_code: 0, working_directory: "/workspace/src" }],
  });
  await settle();

  await type(input(container), "cd src");
  await pressKey(input(container), "Enter");
  await settle();

  assert.equal(container.querySelector(".terminal-cwd-badge").textContent, "/workspace/src");
  assert.match(
    container.querySelector(".terminal-input-row .terminal-prompt-dir").textContent,
    /\/workspace\/src/
  );

  await unmount();
});

test("REQ-037: a stream error is surfaced in the terminal buffer", async () => {
  const { container, unmount } = await renderTerminal({
    events: [{ type: "error", message: "sandbox is unreachable" }],
  });
  await settle();

  await type(input(container), "boom");
  await pressKey(input(container), "Enter");
  await settle();

  assert.match(container.textContent, /sandbox is unreachable/);

  await unmount();
});

test("REQ-037: the command history is navigable with the arrow keys", async () => {
  const { container, unmount } = await renderTerminal();
  await settle();

  await type(input(container), "first");
  await pressKey(input(container), "Enter");
  await settle();

  await type(input(container), "second");
  await pressKey(input(container), "Enter");
  await settle();

  await pressKey(input(container), "ArrowUp");
  assert.equal(input(container).value, "second");

  await pressKey(input(container), "ArrowUp");
  assert.equal(input(container).value, "first");

  await pressKey(input(container), "ArrowDown");
  assert.equal(input(container).value, "second");

  await unmount();
});

test("REQ-037: the quick-action shortcuts dispatch their command", async () => {
  const { container, requests, unmount } = await renderTerminal();
  await settle();

  const quick = container.querySelector(".terminal-quick-btn");
  assert.ok(quick);

  await click(quick);
  await settle();

  assert.ok(requests.some((request) => request.url.includes("/terminal/stream")));

  await unmount();
});

test("REQ-037: the terminal buffer can be cleared", async () => {
  const { container, unmount } = await renderTerminal({
    events: [
      { type: "stdout", data: "output to clear\n" },
      { type: "exit", exit_code: 0, working_directory: "/workspace" },
    ],
  });
  await settle();

  await type(input(container), "echo something");
  await pressKey(input(container), "Enter");
  await settle();

  assert.ok(container.querySelector(".terminal-output-block"));

  await click(container.querySelector('button[title="Clear terminal buffer (Ctrl+L)"]'));
  await settle();

  assert.equal(container.querySelector(".terminal-output-block"), null);

  await unmount();
});
