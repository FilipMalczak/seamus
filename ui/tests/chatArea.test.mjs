/**
 * Component tests for `ChatArea` — the conversation surface.
 *
 * `ChatArea` owns three contracts that are invisible to a static-markup
 * snapshot and that no other test covers:
 *
 *   - INV-008  — the client-side busy guard (submission is disabled while the
 *                thread is not `AWAITING_USER`, or when the thread is closed);
 *   - INV-011  — the composer is focused automatically when a thread opens;
 *   - REQ-032 / INV-039 — the error panel surfaces the `RUN_ERROR` diagnostics
 *                (`error_type` and `traceback`) delivered over the SSE stream.
 *
 * The component is driven through a stubbed `fetch`, so the real
 * `useThreadStream` hook runs its production event-reduction logic against a
 * scripted event stream. No network and no inference are involved.
 */

import assert from "node:assert/strict";
import test, { after, before, beforeEach } from "node:test";

import { click, renderComponent, setupClientDom, type } from "./helpers/clientDom.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

/**
 * Wait inside `act` so a timer-driven React update is flushed, not orphaned.
 *
 * @param {number} ms Milliseconds to wait.
 */
async function settleInAct(ms) {

  const { act } = await import("react");
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms));
  });
}

/**
 * Deliver an AG-UI event to the stream and flush the resulting updates.
 *
 * The delivery happens inside `act` so the hook's state updates are applied
 * before the assertions run.
 *
 * @param {ScriptedStream} stream The scripted stream.
 * @param {object} event The event payload.
 */
async function pushEvent(stream, event) {
  const { act } = await import("react");
  await act(async () => {
    stream.push(event);
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}




let cleanupDom;
let React;
let ChatArea;

const AGENT_ID = "11111111-1111-4111-8111-111111111111";
const SESSION_ID = "22222222-2222-4222-8222-222222222222";
const THREAD_ID = "33333333-3333-4333-8333-333333333333";

/**
 * A controllable SSE endpoint.
 *
 * The stubbed `fetch` returns this for the stream URL; tests push AG-UI events
 * into it and the hook reduces them exactly as it would in the browser.
 */
class ScriptedStream {
  constructor() {
    this.events = [];
    this.listeners = [];
    this.closed = false;
  }

  /**
   * Deliver an AG-UI event to the subscriber.
   *
   * @param {object} event The event payload.
   */
  push(event) {
    if (this.closed) return;
    this.events.push(event);
    for (const listener of this.listeners) listener(event);
  }

  /**
   * The `Response` handed back to the API client.
   *
   * @param {AbortSignal} [signal] The abort signal of the originating fetch.
   * @returns {Response} The streaming response.
   */
  response(signal) {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start: (controller) => {
        this.listeners.push((event) => {
          if (this.closed) return;
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
        });
        // The API client aborts the request when the subscriber unsubscribes.
        // Honouring the signal lets the reader loop terminate, so the test
        // process is not kept alive by a dangling stream.
        signal?.addEventListener("abort", () => {
          this.closed = true;
          try {
            controller.close();
          } catch {
            // The stream may already be closed.
          }
        });
      },
      cancel: () => {
        this.closed = true;
      },
    });
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
  }
}


/**
 * Install a `fetch` stub that serves the endpoints `useThreadStream` uses.
 *
 * @param {object} options Stub options.
 * @returns {{stream: ScriptedStream, calls: Array<object>}} The stub handles.
 */
function installFetchStub(options = {}) {
  const stream = new ScriptedStream();
  const calls = [];

  globalThis.fetch = async (url, init) => {
    const href = String(url);
    calls.push({ url: href, init });

    if (href.includes("/artifact")) {
      return new Response(JSON.stringify(options.artifacts ?? []), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (href.includes("/status")) {
      return new Response(
        JSON.stringify({ status: options.status ?? "AWAITING_USER" }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    if (href.includes("/input")) {
      return new Response(
        JSON.stringify({ status: "AWAITING_LLM", thread_id: THREAD_ID }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    // The thread stream is `.../thread/{id}`; the session stream is
    // `.../session/{id}/stream`. Both are SSE endpoints.
    if (href.includes("/thread/") || href.includes("/stream")) {
      return stream.response(init?.signal);
    }

    return new Response("{}", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });

  };

  return { stream, calls };
}

/**
 * Render the chat area with the given thread state.
 *
 * @param {object} options Render options.
 * @returns {Promise<object>} The render handle plus the stub handles.
 */
async function renderChatArea(options = {}) {
  const stub = installFetchStub(options);

  const handle = await renderComponent(
    React.createElement(ChatArea, {
      agentId: AGENT_ID,
      agentName: "agent",
      sessionId: SESSION_ID,
      sessionName: "session",
      sessionStatus: options.sessionStatus ?? "ACTIVE",
      thread: {
        id: THREAD_ID,
        name: "thread",
        created_at: "2026-01-01T00:00:00Z",
        last_touched_at: "2026-01-01T00:00:00Z",
        is_open: options.isOpen ?? true,
        status: options.status ?? "AWAITING_USER",
        mode: "chat",
        phase: null,
      },
      isSessionView: options.isSessionView ?? false,
    })
  );

  return { ...handle, ...stub };
}

/** The composer textarea. */
function composer(container) {
  return container.querySelector(".composer-textarea");
}

/** The send button. */
function sendButton(container) {
  return container.querySelector(".composer-send-btn");
}

before(async () => {
  cleanupDom = setupClientDom();
  React = (await import("react")).default;
  ({ ChatArea } = await loadModule("components/ChatArea.tsx"));
});

after(async () => {
  await cleanupModules();
  cleanupDom?.cleanup();
});

beforeEach(() => {
  globalThis.alert = () => {};
});

test("INV-008: the composer is enabled for an open, idle thread", async () => {
  const { container, unmount } = await renderChatArea({ status: "AWAITING_USER" });

  assert.equal(composer(container).disabled, false);
  assert.equal(sendButton(container).disabled, true, "an empty composer cannot send");

  await unmount();
});

test("INV-008: the send button is disabled while the thread is busy", async () => {
  const { container, unmount } = await renderChatArea({ status: "AWAITING_LLM" });

  await type(composer(container), "hello");
  assert.equal(sendButton(container).disabled, true);
  assert.equal(sendButton(container).getAttribute("title"), "Agent is busy");

  await unmount();
});

test("INV-008: the composer is disabled for a closed thread", async () => {
  const { container, unmount } = await renderChatArea({ isOpen: false });

  assert.equal(composer(container).disabled, true);
  assert.match(container.textContent, /This thread is closed/);

  await unmount();
});

test("INV-008: a busy thread never posts the user input", async () => {
  const { container, unmount, calls } = await renderChatArea({ status: "AWAITING_LLM" });

  await type(composer(container), "hello");
  await click(sendButton(container));

  assert.equal(
    calls.filter((call) => call.url.includes("/input")).length,
    0,
    "a busy thread must not issue a POST /input"
  );

  await unmount();
});

test("INV-008: an ERROR status is not treated as busy", async () => {
  const { container, unmount } = await renderChatArea({ status: "ERROR" });

  await type(composer(container), "retry please");
  assert.equal(sendButton(container).disabled, false);

  await unmount();
});

test("INV-011: the composer is focused automatically when the thread opens", async () => {
  const { container, unmount } = await renderChatArea({ status: "AWAITING_USER" });

  // The component focuses the composer on a 50ms timer.
  await settleInAct(120);

  assert.equal(document.activeElement, composer(container));

  await unmount();
});

test("INV-011: the composer is focused again after the thread becomes idle", async () => {
  const { container, unmount, stream } = await renderChatArea({ status: "AWAITING_LLM" });

  // The thread is busy, so the auto-focus effect does not run. Drop focus
  // explicitly so the assertion observes the effect, not the `autoFocus`
  // attribute that React applies on mount.
  await settleInAct(120);
  composer(container).blur();
  assert.notEqual(document.activeElement, composer(container));

  // Once the run finishes, the composer is focused again.
  await pushEvent(stream, { type: "RUN_FINISHED" });
  await settleInAct(120);

  assert.equal(document.activeElement, composer(container));

  await unmount();
});



test("REQ-032: the error panel is hidden while the stream is healthy", async () => {
  const { container, unmount } = await renderChatArea();

  assert.equal(container.querySelector(".chat-error-panel"), null);

  await unmount();
});

test("REQ-032: a RUN_ERROR event surfaces the message and the error type", async () => {
  const { container, unmount, stream } = await renderChatArea();

  await pushEvent(stream, {
    type: "RUN_ERROR",
    message: "Simulated upstream provider failure (402 Payment Required)",
    error_type: "RuntimeError",
    traceback: "RuntimeError: Simulated upstream provider failure",
  });

  const panel = container.querySelector(".chat-error-panel");
  assert.ok(panel, "expected the error panel");
  assert.match(panel.textContent, /Simulated upstream provider failure/);
  assert.equal(
    container.querySelector(".chat-error-type-badge").textContent,
    "RuntimeError"
  );

  await unmount();
});

test("REQ-032: the traceback is hidden until it is explicitly expanded", async () => {
  const { container, unmount, stream } = await renderChatArea();

  await pushEvent(stream, {
    type: "RUN_ERROR",
    message: "boom",
    error_type: "RuntimeError",
    traceback: "RuntimeError: boom\n  at <module>",
  });

  assert.equal(container.querySelector(".chat-error-traceback"), null);

  const toggle = container.querySelector('button[title="Show full stack trace"]');
  assert.ok(toggle, "expected a traceback toggle");
  await click(toggle);

  const traceback = container.querySelector(".chat-error-traceback");
  assert.ok(traceback);
  assert.match(traceback.textContent, /RuntimeError: boom/);

  await unmount();
});

test("REQ-032: the error panel offers to copy the full diagnostics", async () => {
  const written = [];
  globalThis.navigator.clipboard = {
    writeText: async (value) => {
      written.push(value);
    },
  };

  const { container, unmount, stream } = await renderChatArea();

  await pushEvent(stream, {
    type: "RUN_ERROR",
    message: "boom",
    error_type: "RuntimeError",
    traceback: "RuntimeError: boom",
  });

  await click(container.querySelector('button[title="Copy full error diagnostics"]'));
  // The button resets its "Copied" label on a 1.8s timer; wait for it so the
  // state update does not land after the test has torn down the DOM.
  await settleInAct(1900);

  assert.equal(written.length, 1);
  assert.match(written[0], /\[RuntimeError\] boom/);
  assert.match(written[0], /RuntimeError: boom/);

  await unmount();
});

test("REQ-032: a RUN_ERROR event moves the thread into the ERROR status", async () => {
  const { container, unmount, stream } = await renderChatArea();

  await pushEvent(stream, {
    type: "RUN_ERROR",
    message: "boom",
    error_type: "RuntimeError",
  });

  // The composer becomes usable again once the thread is in ERROR.
  await type(composer(container), "retry");
  assert.equal(sendButton(container).disabled, false);

  await unmount();
});
