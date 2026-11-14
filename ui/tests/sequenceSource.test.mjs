/**
 * Tests for the production `ui/src/utils/sequence.ts` module.
 *
 * `ui/tests/sequence.test.mjs` re-implements the bubble-extraction and
 * sequence-indexing logic inline. That copy silently drifts from the
 * implementation, so these tests exercise the real module (loaded from
 * `ui/src` via esbuild) and pin the behaviour the UI actually relies on.
 */

import assert from "node:assert/strict";
import test, { after, before } from "node:test";

import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let sequence;

before(async () => {
  sequence = await loadModule("utils/sequence.ts");
});

after(async () => {
  await cleanupModules();
});

function userMessage(id, text = "hi") {
  return { id, role: "user", text, timestamp: "2026-01-02T03:04:05.000Z" };
}

function assistantTextMessage(id, content = "answer") {
  return {
    id,
    role: "assistant",
    text: "",
    timestamp: "2026-01-02T03:04:05.000Z",
    parts: [{ type: "text", id: `${id}-text`, content }],
  };
}

test("extractBubblesFromMessages returns one bubble per user message", () => {
  const bubbles = sequence.extractBubblesFromMessages([
    userMessage("u-1"),
    userMessage("u-2"),
  ]);
  assert.equal(bubbles.length, 2);
  assert.deepEqual(
    bubbles.map((b) => b.key),
    ["u-1", "u-2"]
  );
  assert.ok(bubbles.every((b) => b.role === "user"));
});

test("extractBubblesFromMessages expands assistant parts into separate bubbles", () => {
  const bubbles = sequence.extractBubblesFromMessages([
    {
      id: "a-1",
      role: "assistant",
      text: "",
      timestamp: "2026-01-02T03:04:05.000Z",
      parts: [
        { type: "reasoning", id: "p-reason", content: "thinking" },
        { type: "text", id: "p-text", content: "answer" },
        {
          type: "tool_call",
          id: "p-call",
          toolCall: { id: "call-1", name: "read_file", args: {}, status: "success" },
        },
      ],
    },
  ]);
  assert.deepEqual(
    bubbles.map((b) => b.key),
    ["p-reason", "p-text", "p-call"]
  );
  assert.equal(bubbles[2].toolCallId, "call-1");
});

test("extractBubblesFromMessages skips empty text parts", () => {
  const bubbles = sequence.extractBubblesFromMessages([
    {
      id: "a-1",
      role: "assistant",
      text: "",
      timestamp: "2026-01-02T03:04:05.000Z",
      parts: [
        { type: "text", id: "p-empty", content: "   " },
        { type: "text", id: "p-text", content: "answer" },
      ],
    },
  ]);
  assert.deepEqual(
    bubbles.map((b) => b.key),
    ["p-text"]
  );
});

test("extractBubblesFromMessages treats thread transitions as boundaries", () => {
  const bubbles = sequence.extractBubblesFromMessages([
    userMessage("u-1"),
    {
      id: "t-1",
      role: "system",
      text: "",
      timestamp: "2026-01-02T03:04:05.000Z",
      threadTransition: { threadId: "thread-2", mode: "plan" },
    },
    userMessage("u-2"),
  ]);
  assert.equal(bubbles.length, 3);
  assert.equal(bubbles[1].role, "boundary");
});

test("extractBubblesFromMessages treats synthetic messages as boundaries", () => {
  const bubbles = sequence.extractBubblesFromMessages([
    userMessage("u-1"),
    userMessage("s-1", "<SYNTHETIC MESSAGE INDICATOR> continue"),
  ]);
  assert.equal(bubbles.length, 2);
  assert.equal(bubbles[1].role, "boundary");
});

test("computeBubbleSequenceIndices leaves short streaks unindexed", () => {
  const messages = [
    assistantTextMessage("a-1"),
    assistantTextMessage("a-2"),
    assistantTextMessage("a-3"),
  ];
  const indices = sequence.computeBubbleSequenceIndices(messages);
  assert.equal(indices.size, 0);
});

test("computeBubbleSequenceIndices indexes streaks above the threshold", () => {
  const messages = [];
  for (let i = 1; i <= 6; i++) {
    messages.push(assistantTextMessage(`a-${i}`));
  }
  const indices = sequence.computeBubbleSequenceIndices(messages);
  assert.equal(indices.get("a-1-text"), 1);
  assert.equal(indices.get("a-6-text"), 6);
});

test("computeBubbleSequenceIndices resets the streak on a role change", () => {
  const messages = [
    assistantTextMessage("a-1"),
    assistantTextMessage("a-2"),
    assistantTextMessage("a-3"),
    userMessage("u-1"),
    assistantTextMessage("a-4"),
    assistantTextMessage("a-5"),
    assistantTextMessage("a-6"),
  ];
  const indices = sequence.computeBubbleSequenceIndices(messages);
  // The trailing assistant streak is 3 long — below the threshold.
  assert.equal(indices.get("a-4-text"), undefined);
  assert.equal(indices.get("a-6-text"), undefined);
});

test("computeBubbleSequenceIndices honours a custom threshold", () => {
  const messages = [
    assistantTextMessage("a-1"),
    assistantTextMessage("a-2"),
    assistantTextMessage("a-3"),
  ];
  const indices = sequence.computeBubbleSequenceIndices(messages, 2);
  assert.equal(indices.get("a-1-text"), 1);
  assert.equal(indices.get("a-3-text"), 3);
});

test("computeBubbleSequenceIndices aliases tool call ids to their part id", () => {
  const messages = [];
  for (let i = 1; i <= 6; i++) {
    messages.push({
      id: `a-${i}`,
      role: "assistant",
      text: "",
      timestamp: "2026-01-02T03:04:05.000Z",
      parts: [
        {
          type: "tool_call",
          id: `p-call-${i}`,
          toolCall: {
            id: `call-${i}`,
            name: "read_file",
            args: {},
            status: "success",
          },
        },
      ],
    });
  }
  const indices = sequence.computeBubbleSequenceIndices(messages);
  assert.equal(indices.get("p-call-1"), 1);
  assert.equal(indices.get("call-1"), 1);
  assert.equal(indices.get("call-6"), 6);
});

test("formatBubbleTime renders an empty string for missing or invalid input", () => {
  assert.equal(sequence.formatBubbleTime(undefined), "");
  assert.equal(sequence.formatBubbleTime(null), "");
  assert.equal(sequence.formatBubbleTime("not-a-date"), "");
});

test("formatBubbleTime renders seconds precision for a valid ISO timestamp", () => {
  const formatted = sequence.formatBubbleTime("2026-01-02T03:04:05.000Z");
  assert.match(formatted, /\d{2}:\d{2}:\d{2}/);
});

test("formatFullDate includes the ISO timestamp", () => {
  const formatted = sequence.formatFullDate("2026-01-02T03:04:05.000Z");
  assert.match(formatted, /2026-01-02T03:04:05\.000Z/);
});

test("formatFullDate returns the raw input when it cannot be parsed", () => {
  assert.equal(sequence.formatFullDate("not-a-date"), "not-a-date");
});
