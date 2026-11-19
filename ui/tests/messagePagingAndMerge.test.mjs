/**
 * Pure logic and state transition unit tests for bubble extraction,
 * message merging (prepend/append), and memory pruning.
 */

import assert from "node:assert/strict";
import test, { after, before } from "node:test";

import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let extractBubblesFromMessages;
let prependMessages;
let appendMessages;

before(async () => {
  const seqMod = await loadModule("utils/sequence.ts");
  extractBubblesFromMessages = seqMod.extractBubblesFromMessages;

  const streamMod = await loadModule("hooks/useThreadStream.ts");
  prependMessages = streamMod.prependMessages;
  appendMessages = streamMod.appendMessages;
});

after(async () => {
  await cleanupModules();
});

test("extractBubblesFromMessages extracts stable keys for mixed complex turns", () => {
  const messages = [
    {
      id: "transition-thread-1",
      role: "system",
      text: "",
      threadTransition: { threadId: "thread-1", mode: "chat", phase: null },
    },
    {
      id: "user-1",
      role: "user",
      text: "Run diagnostics",
    },
    {
      id: "asst-1",
      role: "assistant",
      text: "Starting diagnostics now.",
      parts: [
        { type: "reasoning", id: "reasoning-1", content: "Plan steps", isStreaming: false },
        { type: "tool_call", id: "call-1", toolCall: { id: "call-1", name: "ls", status: "done" } },
        { type: "tool_call", id: "call-2", toolCall: { id: "call-2", name: "ps", status: "done" } },
        { type: "text", id: "text-1", content: "Found 2 processes." },
        { type: "text", id: "text-empty", content: "   " }, // Should be skipped
      ],
      toolCalls: [
        { id: "call-1", name: "ls", status: "done" },
        { id: "call-2", name: "ps", status: "done" },
      ],
    },
  ];

  const bubbles = extractBubblesFromMessages(messages);
  assert.equal(bubbles.length, 6);
  assert.equal(bubbles[0].key, "transition-thread-1");
  assert.equal(bubbles[1].key, "user-1");
  assert.equal(bubbles[2].key, "reasoning-1");
  assert.equal(bubbles[3].key, "call-1");
  assert.equal(bubbles[4].key, "call-2");
  assert.equal(bubbles[5].key, "text-1");
});

test("prependMessages handles disjoint older messages", () => {
  const prev = [
    { id: "user-2", role: "user", text: "Second user" },
    { id: "asst-2", role: "assistant", text: "Second bot" },
  ];
  const incoming = [
    { id: "user-1", role: "user", text: "First user" },
    { id: "asst-1", role: "assistant", text: "First bot" },
  ];

  const merged = prependMessages(prev, incoming);
  assert.equal(merged.length, 4);
  assert.deepEqual(merged.map((m) => m.id), ["user-1", "asst-1", "user-2", "asst-2"]);
});

test("prependMessages merges older parts into existing assistant message", () => {
  const prev = [
    {
      id: "asst-1",
      role: "assistant",
      text: "second half",
      parts: [
        { type: "tool_call", id: "call-3", toolCall: { id: "call-3", name: "t3" } },
        { type: "tool_call", id: "call-4", toolCall: { id: "call-4", name: "t4" } },
      ],
      toolCalls: [
        { id: "call-3", name: "t3" },
        { id: "call-4", name: "t4" },
      ],
    },
  ];

  const incoming = [
    { id: "user-1", role: "user", text: "Start run" },
    {
      id: "asst-1",
      role: "assistant",
      text: "first half",
      parts: [
        { type: "reasoning", id: "reasoning-1", content: "think" },
        { type: "tool_call", id: "call-1", toolCall: { id: "call-1", name: "t1" } },
        { type: "tool_call", id: "call-2", toolCall: { id: "call-2", name: "t2" } },
      ],
      toolCalls: [
        { id: "call-1", name: "t1" },
        { id: "call-2", name: "t2" },
      ],
    },
  ];

  const merged = prependMessages(prev, incoming);
  assert.equal(merged.length, 2);
  assert.equal(merged[0].id, "user-1");
  assert.equal(merged[1].id, "asst-1");

  // Parts should be in chronological order: reasoning-1, call-1, call-2, call-3, call-4
  const partIds = merged[1].parts.map((p) => p.id);
  assert.deepEqual(partIds, ["reasoning-1", "call-1", "call-2", "call-3", "call-4"]);

  const callIds = merged[1].toolCalls.map((tc) => tc.id);
  assert.deepEqual(callIds, ["call-1", "call-2", "call-3", "call-4"]);
});

test("appendMessages merges newer parts into existing assistant message", () => {
  const prev = [
    {
      id: "asst-1",
      role: "assistant",
      text: "first half",
      parts: [
        { type: "reasoning", id: "reasoning-1", content: "think" },
        { type: "tool_call", id: "call-1", toolCall: { id: "call-1", name: "t1" } },
      ],
      toolCalls: [{ id: "call-1", name: "t1" }],
    },
  ];

  const incoming = [
    {
      id: "asst-1",
      role: "assistant",
      text: "second half",
      parts: [
        { type: "tool_call", id: "call-2", toolCall: { id: "call-2", name: "t2" } },
        { type: "text", id: "text-1", content: "done" },
      ],
      toolCalls: [{ id: "call-2", name: "t2" }],
    },
    { id: "user-2", role: "user", text: "Followup" },
  ];

  const merged = appendMessages(prev, incoming);
  assert.equal(merged.length, 2);
  assert.equal(merged[0].id, "asst-1");
  assert.equal(merged[1].id, "user-2");

  const partIds = merged[0].parts.map((p) => p.id);
  assert.deepEqual(partIds, ["reasoning-1", "call-1", "call-2", "text-1"]);

  const callIds = merged[0].toolCalls.map((tc) => tc.id);
  assert.deepEqual(callIds, ["call-1", "call-2"]);
});

test("prependMessages and appendMessages handle empty inputs without mutation", () => {
  const msgs = [{ id: "m1", role: "user", text: "test" }];
  assert.equal(prependMessages(msgs, []), msgs);
  assert.equal(prependMessages([], msgs), msgs);
  assert.equal(appendMessages(msgs, []), msgs);
  assert.equal(appendMessages([], msgs), msgs);
});

test("memory pruning cuts out-of-range bubbles while preserving turn wrappers", () => {
  // Simulate 100 tool call parts in asst-1
  const parts = Array.from({ length: 100 }, (_, i) => ({
    type: "tool_call",
    id: `call-${i}`,
    toolCall: { id: `call-${i}`, name: "cmd" },
  }));
  const toolCalls = Array.from({ length: 100 }, (_, i) => ({
    id: `call-${i}`,
    name: "cmd",
  }));

  const messages = [
    { id: "user-1", role: "user", text: "Run 100 steps" },
    { id: "asst-1", role: "assistant", text: "", parts, toolCalls },
  ];

  const bubbles = extractBubblesFromMessages(messages);
  assert.equal(bubbles.length, 101); // 1 user + 100 calls

  // Anchor at call-50 (bubble index 51)
  const anchorBubbleId = "call-50";
  const anchorIdx = bubbles.findIndex((b) => b.key === anchorBubbleId);
  assert.equal(anchorIdx, 51);

  const memoryLimit = 20; // Keep at most 20 before and 20 after = 41 bubbles
  const keepStartBubble = Math.max(0, anchorIdx - memoryLimit);
  const keepEndBubble = Math.min(bubbles.length, anchorIdx + memoryLimit + 1);

  const keepBubbles = new Set(
    bubbles.slice(keepStartBubble, keepEndBubble).map((b) => b.key)
  );

  const pruned = [];
  for (const m of messages) {
    if (m.role === "user") {
      if (keepBubbles.has(m.id)) pruned.push(m);
    } else if (m.parts && m.parts.length > 0) {
      const keptParts = m.parts.filter((p) => keepBubbles.has(p.id));
      if (keptParts.length > 0) {
        const keptCalls = m.toolCalls?.filter((tc) => keepBubbles.has(tc.id));
        pruned.push({ ...m, parts: keptParts, toolCalls: keptCalls });
      }
    }
  }

  // user-1 was bubble 0, which is outside [31..72], so it should be pruned
  assert.equal(pruned.length, 1);
  assert.equal(pruned[0].id, "asst-1");
  // asst-1 retained exactly 41 parts (call-30 to call-70)
  assert.equal(pruned[0].parts.length, 41);
  assert.equal(pruned[0].parts[0].id, "call-30");
  assert.equal(pruned[0].parts[40].id, "call-70");
});

