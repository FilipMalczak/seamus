/**
 * Unit & component tests for ChatArea pagination, UI windowing, and memory buffering.
 */

import assert from "node:assert/strict";
import test, { after, before, beforeEach } from "node:test";

import { click, renderComponent, setupClientDom } from "./helpers/clientDom.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let cleanupDom;
let React;
let ChatArea;

class ScriptedStream {
  constructor() {
    this.listeners = [];
  }
  response(signal) {
    const body = new ReadableStream({
      start: (controller) => {
        const listener = (event) => {
          try {
            controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`));
          } catch {
            // ignore
          }
        };
        this.listeners.push(listener);
        signal?.addEventListener("abort", () => {
          this.listeners = this.listeners.filter((l) => l !== listener);
        });
      },
    });
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
  }
  push(event) {
    for (const l of this.listeners) l(event);
  }
}

async function settleInAct(ms = 30) {
  const { act } = await import("react");
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms));
  });
}

function installFetchStub(options = {}) {
  const recorded = [];
  const stream = new ScriptedStream();

  globalThis.fetch = async (url, init) => {
    const href = String(url);
    recorded.push({ url: href, method: init?.method ?? "GET" });

    if (href.includes("/messages")) {
      const messages = options.messages ?? [];
      const limit = options.limit ?? 50;
      return new Response(
        JSON.stringify({
          messages: messages.slice(0, limit),
          total_bubbles: messages.length,
          has_more_before: Boolean(options.has_more_before),
          has_more_after: Boolean(options.has_more_after),
          oldest_bubble_id: messages[0]?.id || null,
          newest_bubble_id: messages[messages.length - 1]?.id || null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }

    if (href.includes("/artifact")) {
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (href.includes("/status")) {
      return new Response(JSON.stringify({ status: "AWAITING_USER" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (href.includes("/stream") || href.includes("/thread/")) {
      return stream.response(init?.signal);
    }

    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  return { recorded, stream };
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

test("REQ-071: ChatArea loads latest tail batch of messages on initial mount", async () => {
  const mockMessages = Array.from({ length: 50 }, (_, i) => ({
    id: `msg-${i}`,
    role: "user",
    text: `Message ${i}`,
    timestamp: new Date().toISOString(),
  }));

  const { recorded } = installFetchStub({
    messages: mockMessages,
    has_more_before: true,
  });

  const { container, unmount } = await renderComponent(
    React.createElement(ChatArea, {
      agentId: "agent-1",
      sessionId: "session-1",
      thread: null,
      isSessionView: true,
      apiBatchSize: 50,
      uiBatchSize: 200,
      memoryBatchSize: 300,
    })
  );

  await settleInAct(50);

  // Assert API messages endpoint was called with tail=true
  const messagesReq = recorded.find((r) => r.url.includes("/messages"));
  assert.ok(messagesReq, "Messages endpoint was called");
  assert.match(messagesReq.url, /tail=true/);
  assert.match(messagesReq.url, /limit=50/);

  // Assert stream was connected with replay=false
  const streamReq = recorded.find((r) => r.url.includes("/stream"));
  assert.ok(streamReq, "SSE stream was connected");
  assert.match(streamReq.url, /replay=false/);

  await unmount();
});

test("REQ-071: ChatArea applies UI windowing to limit rendered DOM elements", async () => {
  // Create 30 mock messages
  const mockMessages = Array.from({ length: 30 }, (_, i) => ({
    id: `msg-${i}`,
    role: "user",
    text: `Message ${i}`,
    timestamp: new Date().toISOString(),
  }));

  installFetchStub({
    messages: mockMessages,
    limit: 30,
    has_more_before: true,
  });

  // UI batch size 5 (renders at most 5 before + 5 after anchor = at most ~11 bubbles)
  const { container, unmount } = await renderComponent(
    React.createElement(ChatArea, {
      agentId: "agent-1",
      sessionId: "session-1",
      thread: null,
      isSessionView: true,
      apiBatchSize: 5,
      uiBatchSize: 5,
      memoryBatchSize: 20,
    })
  );

  await settleInAct(50);

  const renderedBubbles = container.querySelectorAll("[data-bubble-id]");
  // Total in DOM should be strictly less than all 30 bubbles
  assert.ok(
    renderedBubbles.length <= 12,
    `Rendered bubbles (${renderedBubbles.length}) is windowed below total messages (30)`
  );

  await unmount();
});

test("REQ-071: ChatArea applies UI windowing to parts within a single assistant message", async () => {
  const parts = Array.from({ length: 30 }, (_, i) => ({
    type: "reasoning",
    id: `reasoning-${i}`,
    content: `Step ${i}`,
  }));
  const assistantMsg = {
    id: "asst-1",
    role: "assistant",
    text: "",
    parts,
    timestamp: new Date().toISOString(),
  };

  installFetchStub({
    messages: [assistantMsg],
    limit: 1,
    has_more_before: true,
  });

  const { container, unmount } = await renderComponent(
    React.createElement(ChatArea, {
      agentId: "agent-1",
      sessionId: "session-1",
      thread: null,
      isSessionView: true,
      apiBatchSize: 5,
      uiBatchSize: 5,
      memoryBatchSize: 20,
    })
  );

  await settleInAct(50);

  const renderedBubbles = container.querySelectorAll("[data-bubble-id]");
  assert.ok(
    renderedBubbles.length <= 12,
    `Rendered bubbles within assistant turn (${renderedBubbles.length}) is windowed below 30`
  );

  await unmount();
});
