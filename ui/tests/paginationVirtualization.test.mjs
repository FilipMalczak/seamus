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

const mockThread = {
  id: "thread-1",
  mode: "chat",
  phase: null,
  is_open: true,
  status: "AWAITING_USER",
};

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
      if (options.pagedHandler) {
        const res = options.pagedHandler(href);
        return new Response(JSON.stringify(res), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

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
      thread: mockThread,
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
      thread: mockThread,
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
      thread: mockThread,
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

test("REQ-071: Upward scrolling near top triggers before_id fetch and prepends older messages", async () => {
  const allBubbles = Array.from({ length: 100 }, (_, i) => ({
    id: `msg-${i}`,
    role: "user",
    text: `User prompt ${i}`,
    timestamp: new Date().toISOString(),
  }));

  const pagedHandler = (href) => {
    const url = new URL(href, "http://localhost");
    const limit = parseInt(url.searchParams.get("limit") || "10", 10);
    const beforeId = url.searchParams.get("before_id");

    if (beforeId) {
      const idx = allBubbles.findIndex((b) => b.id === beforeId);
      const end = idx >= 0 ? idx : allBubbles.length;
      const start = Math.max(0, end - limit);
      const slice = allBubbles.slice(start, end);
      return {
        messages: slice,
        total_bubbles: allBubbles.length,
        has_more_before: start > 0,
        has_more_after: true,
        oldest_bubble_id: slice[0]?.id || null,
        newest_bubble_id: slice[slice.length - 1]?.id || null,
      };
    }

    // Default tail 10
    const start = allBubbles.length - limit;
    const slice = allBubbles.slice(start);
    return {
      messages: slice,
      total_bubbles: allBubbles.length,
      has_more_before: true,
      has_more_after: false,
      oldest_bubble_id: slice[0]?.id || null,
      newest_bubble_id: slice[slice.length - 1]?.id || null,
    };
  };

  const { recorded } = installFetchStub({ pagedHandler });

  const { container, unmount } = await renderComponent(
    React.createElement(ChatArea, {
      agentId: "agent-1",
      sessionId: "session-1",
      thread: mockThread,
      isSessionView: true,
      apiBatchSize: 10,
      uiBatchSize: 50,
      memoryBatchSize: 100,
    })
  );

  await settleInAct(50);

  // Initial load fetched tail (msg-90 to msg-99)
  assert.ok(container.querySelector("[data-bubble-id='msg-95']"));
  assert.equal(container.querySelector("[data-bubble-id='msg-85']"), null);

  const viewport = container.querySelector(".chat-viewport");
  assert.ok(viewport, "Viewport container exists");

  // Simulate scrolling to top: scrollTop = 50 (< 120 trigger)
  Object.defineProperty(viewport, "scrollTop", { value: 50, writable: true });
  Object.defineProperty(viewport, "scrollHeight", { value: 2000, writable: true });
  Object.defineProperty(viewport, "clientHeight", { value: 600, writable: true });

  const { act } = await import("react");
  await act(async () => {
    viewport.dispatchEvent(new Event("scroll"));
  });

  await settleInAct(50);

  // Assert that a before_id request was sent for msg-90
  const beforeReq = recorded.find((r) => r.url.includes("before_id=msg-90"));
  assert.ok(beforeReq, "Dispatched before_id request for oldest bubble");

  // Assert that older messages are now present in the document
  assert.ok(container.querySelector("[data-bubble-id='msg-85']"), "Prepended msg-85 is mounted");

  await unmount();
});

test("REQ-071: Downward scrolling near bottom triggers after_id fetch when hasMoreAfter is true", async () => {
  const allBubbles = Array.from({ length: 60 }, (_, i) => ({
    id: `msg-${i}`,
    role: "user",
    text: `User prompt ${i}`,
    timestamp: new Date().toISOString(),
  }));

  const pagedHandler = (href) => {
    const url = new URL(href, "http://localhost");
    const limit = parseInt(url.searchParams.get("limit") || "10", 10);
    const afterId = url.searchParams.get("after_id");

    if (afterId) {
      const idx = allBubbles.findIndex((b) => b.id === afterId);
      const start = idx >= 0 ? idx + 1 : 0;
      const end = Math.min(allBubbles.length, start + limit);
      const slice = allBubbles.slice(start, end);
      return {
        messages: slice,
        total_bubbles: allBubbles.length,
        has_more_before: true,
        has_more_after: end < allBubbles.length,
        oldest_bubble_id: slice[0]?.id || null,
        newest_bubble_id: slice[slice.length - 1]?.id || null,
      };
    }

    // Return slice 20..29 so has_more_after is true
    const slice = allBubbles.slice(20, 30);
    return {
      messages: slice,
      total_bubbles: allBubbles.length,
      has_more_before: true,
      has_more_after: true,
      oldest_bubble_id: "msg-20",
      newest_bubble_id: "msg-29",
    };
  };

  const { recorded } = installFetchStub({ pagedHandler });

  const { container, unmount } = await renderComponent(
    React.createElement(ChatArea, {
      agentId: "agent-1",
      sessionId: "session-1",
      thread: mockThread,
      isSessionView: true,
      apiBatchSize: 10,
      uiBatchSize: 50,
      memoryBatchSize: 100,
    })
  );

  await settleInAct(50);

  const viewport = container.querySelector(".chat-viewport");
  assert.ok(viewport, "Viewport container exists");

  // Scroll near bottom: scrollHeight (2000) - scrollTop (1400) - clientHeight (600) = 0 < 120
  Object.defineProperty(viewport, "scrollTop", { value: 1400, writable: true });
  Object.defineProperty(viewport, "scrollHeight", { value: 2000, writable: true });
  Object.defineProperty(viewport, "clientHeight", { value: 600, writable: true });

  const { act } = await import("react");
  await act(async () => {
    viewport.dispatchEvent(new Event("scroll"));
  });

  await settleInAct(50);

  // Assert after_id request was dispatched for msg-29
  const afterReq = recorded.find((r) => r.url.includes("after_id=msg-29"));
  assert.ok(afterReq, "Dispatched after_id request for newest bubble");

  await unmount();
});

test("REQ-071: Clicking 'Scroll to bottom' jumps directly to tail batch and resets hasMoreAfter", async () => {
  const allBubbles = Array.from({ length: 100 }, (_, i) => ({
    id: `msg-${i}`,
    role: "user",
    text: `User prompt ${i}`,
    timestamp: new Date().toISOString(),
  }));

  const pagedHandler = (href) => {
    const url = new URL(href, "http://localhost");
    const tail = url.searchParams.get("tail") === "true";
    const beforeId = url.searchParams.get("before_id");

    if (beforeId) {
      const idx = allBubbles.findIndex((b) => b.id === beforeId);
      const end = idx >= 0 ? idx : allBubbles.length;
      const start = Math.max(0, end - 10);
      const slice = allBubbles.slice(start, end);
      return {
        messages: slice,
        total_bubbles: 100,
        has_more_before: start > 0,
        has_more_after: true,
        oldest_bubble_id: slice[0]?.id || null,
        newest_bubble_id: slice[slice.length - 1]?.id || null,
      };
    }

    if (tail) {
      const slice = allBubbles.slice(90, 100);
      return {
        messages: slice,
        total_bubbles: 100,
        has_more_before: true,
        has_more_after: false,
        oldest_bubble_id: "msg-90",
        newest_bubble_id: "msg-99",
      };
    }

    const slice = allBubbles.slice(90, 100);
    return {
      messages: slice,
      total_bubbles: 100,
      has_more_before: true,
      has_more_after: false,
      oldest_bubble_id: "msg-90",
      newest_bubble_id: "msg-99",
    };
  };

  const { recorded } = installFetchStub({ pagedHandler });

  const { container, unmount } = await renderComponent(
    React.createElement(ChatArea, {
      agentId: "agent-1",
      sessionId: "session-1",
      thread: mockThread,
      isSessionView: true,
      apiBatchSize: 10,
      uiBatchSize: 50,
      memoryBatchSize: 100,
    })
  );

  await settleInAct(50);

  const viewport = container.querySelector(".chat-viewport");
  assert.ok(viewport, "Viewport container exists");

  // User scrolls up into history: scrollTop = 50 (away from bottom)
  Object.defineProperty(viewport, "scrollTop", { value: 50, writable: true });
  Object.defineProperty(viewport, "scrollHeight", { value: 2000, writable: true });
  Object.defineProperty(viewport, "clientHeight", { value: 600, writable: true });

  const { act } = await import("react");
  await act(async () => {
    viewport.dispatchEvent(new Event("scroll"));
  });

  await settleInAct(50);

  // Since user scrolled up into history, the scroll-to-bottom button should appear
  const scrollBtn = container.querySelector(".scroll-to-bottom-btn");
  assert.ok(scrollBtn, "Scroll-to-bottom jump button is rendered when scrolled into history");

  await act(async () => {
    click(scrollBtn);
  });

  await settleInAct(50);

  // Verify jumpToLatest called tail=true
  const tailReqs = recorded.filter((r) => r.url.includes("tail=true"));
  assert.ok(tailReqs.length >= 2, "jumpToLatest dispatched tail=true request");

  // Verify latest messages are rendered
  assert.ok(container.querySelector("[data-bubble-id='msg-99']"), "msg-99 is rendered after jumping");

  await unmount();
});

test("REQ-071: Live streaming events append to the active message during turn", async () => {
  const initialMsg = {
    id: "asst-live",
    role: "assistant",
    text: "Initial part",
    parts: [{ type: "text", id: "text-init", content: "Initial part" }],
    timestamp: new Date().toISOString(),
  };

  const { stream } = installFetchStub({
    messages: [initialMsg],
    has_more_before: false,
  });

  const { container, unmount } = await renderComponent(
    React.createElement(ChatArea, {
      agentId: "agent-1",
      sessionId: "session-1",
      thread: mockThread,
      isSessionView: true,
      apiBatchSize: 10,
      uiBatchSize: 50,
      memoryBatchSize: 100,
    })
  );

  await settleInAct(50);

  const { act } = await import("react");
  await act(async () => {
    // Push live text chunk over SSE
    stream.push({
      type: "TEXT_MESSAGE_CHUNK",
      message_id: "asst-live",
      delta: " ...more live tokens",
    });
  });

  await settleInAct(50);

  const bubbleText = container.textContent || "";
  assert.ok(bubbleText.includes("more live tokens"), "Live streamed text appears in UI bubble");

  await unmount();
});
