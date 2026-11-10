import assert from "node:assert/strict";
import test from "node:test";

const BUBBLE_SEQUENCE_THRESHOLD = 5;
const SYNTHETIC_MESSAGE_INDICATOR = "<SYNTHETIC MESSAGE INDICATOR>";

function extractBubblesFromMessages(messages) {
  const bubbles = [];

  for (let mIdx = 0; mIdx < messages.length; mIdx++) {
    const msg = messages[mIdx];
    if (msg.threadTransition) {
      bubbles.push({ key: `transition-${mIdx}`, role: "boundary" });
      continue;
    }

    const isSynthetic = Boolean(
      msg.text?.startsWith(SYNTHETIC_MESSAGE_INDICATOR)
    );
    if (isSynthetic) {
      bubbles.push({ key: `synthetic-${mIdx}`, role: "boundary" });
      continue;
    }

    if (msg.role === "user") {
      bubbles.push({ key: msg.id || `user-${mIdx}`, role: "user" });
      continue;
    }

    if (msg.role === "assistant") {
      if (msg.parts && msg.parts.length > 0) {
        for (let pIdx = 0; pIdx < msg.parts.length; pIdx++) {
          const part = msg.parts[pIdx];
          if (part.type === "reasoning") {
            bubbles.push({ key: part.id, role: "assistant" });
          } else if (part.type === "tool_call") {
            bubbles.push({
              key: part.id,
              role: "assistant",
              toolCallId: part.toolCall?.id,
            });
          } else if (part.type === "artifact") {
            bubbles.push({ key: part.id, role: "assistant" });
          } else if (part.type === "text") {
            if (part.content && part.content.trim().length > 0) {
              bubbles.push({ key: part.id, role: "assistant" });
            }
          }
        }
      } else {
        if (msg.reasoning || msg.isReasoning) {
          bubbles.push({ key: `${msg.id}-reasoning`, role: "assistant" });
        }
        if (msg.toolCalls && msg.toolCalls.length > 0) {
          for (const tc of msg.toolCalls) {
            bubbles.push({
              key: tc.id,
              role: "assistant",
              toolCallId: tc.id,
            });
          }
        }
        if (msg.text && msg.text.trim().length > 0) {
          bubbles.push({ key: `${msg.id}-text`, role: "assistant" });
        }
      }
    }
  }

  return bubbles;
}

function computeBubbleSequenceIndices(messages, threshold = BUBBLE_SEQUENCE_THRESHOLD) {
  const result = new Map();
  const bubbles = extractBubblesFromMessages(messages);

  let currentStreakRole = null;
  let currentStreak = [];

  const flushStreak = () => {
    if (currentStreak.length > threshold) {
      currentStreak.forEach((bubble, stepIdx) => {
        result.set(bubble.key, stepIdx + 1);
        if (bubble.toolCallId && bubble.toolCallId !== bubble.key) {
          result.set(bubble.toolCallId, stepIdx + 1);
        }
      });
    }
    currentStreak = [];
    currentStreakRole = null;
  };

  for (const b of bubbles) {
    if (b.role !== "user" && b.role !== "assistant") {
      flushStreak();
      continue;
    }

    if (b.role === currentStreakRole) {
      currentStreak.push(b);
    } else {
      flushStreak();
      currentStreakRole = b.role;
      currentStreak.push(b);
    }
  }

  flushStreak();

  // Populate secondary lookup aliases
  for (let mIdx = 0; mIdx < messages.length; mIdx++) {
    const msg = messages[mIdx];
    if (msg.role === "assistant" && msg.parts) {
      for (const p of msg.parts) {
        if (p.type === "tool_call" && p.toolCall?.id) {
          const idx = result.get(p.id) ?? result.get(p.toolCall.id);
          if (idx !== undefined) {
            result.set(p.id, idx);
            result.set(p.toolCall.id, idx);
          }
        }
      }
    }
    const msgAlias =
      result.get(`${msg.id}-text`) ??
      result.get(msg.id) ??
      (msg.parts?.length === 1 ? result.get(msg.parts[0].id) : undefined);
    if (msgAlias !== undefined) {
      result.set(msg.id, msgAlias);
    }
  }

  return result;
}

function formatBubbleTime(isoString) {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "";
  }
}

function formatFullDate(isoString) {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return `${d.toLocaleString()} (${d.toISOString()})`;
  } catch {
    return isoString;
  }
}

test("computeBubbleSequenceIndices - empty messages", () => {
  const result = computeBubbleSequenceIndices([]);
  assert.equal(result.size, 0);
});

test("computeBubbleSequenceIndices - streak at or below threshold (<= 5) gets no indices", () => {
  const messages = [
    { id: "m1", role: "assistant", text: "step 1" },
    { id: "m2", role: "assistant", text: "step 2" },
    { id: "m3", role: "assistant", text: "step 3" },
    { id: "m4", role: "assistant", text: "step 4" },
    { id: "m5", role: "assistant", text: "step 5" },
  ];

  const result = computeBubbleSequenceIndices(messages, 5);
  assert.equal(result.size, 0);
});

test("computeBubbleSequenceIndices - streak of 6 separate assistant messages gets 1-based indices", () => {
  const messages = [
    { id: "m1", role: "assistant", text: "step 1" },
    { id: "m2", role: "assistant", text: "step 2" },
    { id: "m3", role: "assistant", text: "step 3" },
    { id: "m4", role: "assistant", text: "step 4" },
    { id: "m5", role: "assistant", text: "step 5" },
    { id: "m6", role: "assistant", text: "step 6" },
  ];

  const result = computeBubbleSequenceIndices(messages, 5);
  assert.equal(result.get("m1"), 1);
  assert.equal(result.get("m2"), 2);
  assert.equal(result.get("m3"), 3);
  assert.equal(result.get("m4"), 4);
  assert.equal(result.get("m5"), 5);
  assert.equal(result.get("m6"), 6);
});

test("computeBubbleSequenceIndices - multi-part assistant message (> 5 bubbles) gets indexed", () => {
  // A single assistant message containing 3 reasoning blocks and 3 tool calls = 6 bubbles
  const messages = [
    { id: "u1", role: "user", text: "Run autonomous tasks" },
    {
      id: "asst-1",
      role: "assistant",
      parts: [
        { type: "reasoning", id: "r1", content: "Thinking 1" },
        { type: "tool_call", id: "tc1-part", toolCall: { id: "tc1", name: "bash" } },
        { type: "reasoning", id: "r2", content: "Thinking 2" },
        { type: "tool_call", id: "tc2-part", toolCall: { id: "tc2", name: "read_file" } },
        { type: "reasoning", id: "r3", content: "Thinking 3" },
        { type: "tool_call", id: "tc3-part", toolCall: { id: "tc3", name: "write_file" } },
      ],
    },
  ];

  const result = computeBubbleSequenceIndices(messages, 5);
  assert.equal(result.get("r1"), 1);
  assert.equal(result.get("tc1-part"), 2);
  assert.equal(result.get("tc1"), 2);
  assert.equal(result.get("r2"), 3);
  assert.equal(result.get("tc2-part"), 4);
  assert.equal(result.get("tc2"), 4);
  assert.equal(result.get("r3"), 5);
  assert.equal(result.get("tc3-part"), 6);
  assert.equal(result.get("tc3"), 6);
  // User message was 1 bubble, <= 5 threshold, so not indexed
  assert.equal(result.get("u1"), undefined);
});

test("computeBubbleSequenceIndices - thread transition resets streaks", () => {
  const messages = [
    { id: "m1", role: "assistant", text: "turn 1" },
    { id: "m2", role: "assistant", text: "turn 2" },
    { id: "m3", role: "assistant", text: "turn 3" },
    { id: "m4", role: "assistant", text: "turn 4" },
    {
      id: "tr1",
      role: "system",
      threadTransition: { threadId: "t-2", mode: "plan" },
    },
    { id: "m5", role: "assistant", text: "turn 5" },
    { id: "m6", role: "assistant", text: "turn 6" },
  ];

  const result = computeBubbleSequenceIndices(messages, 5);
  assert.equal(result.size, 0);
});

test("computeBubbleSequenceIndices - synthetic event breaks streak", () => {
  const messages = [
    { id: "m1", role: "assistant", text: "turn 1" },
    { id: "m2", role: "assistant", text: "turn 2" },
    { id: "m3", role: "assistant", text: "turn 3" },
    { id: "m4", role: "assistant", text: `${SYNTHETIC_MESSAGE_INDICATOR} User unblocked` },
    { id: "m5", role: "assistant", text: "turn 4" },
    { id: "m6", role: "assistant", text: "turn 5" },
    { id: "m7", role: "assistant", text: "turn 6" },
  ];

  const result = computeBubbleSequenceIndices(messages, 5);
  assert.equal(result.size, 0);
});

test("computeBubbleSequenceIndices - custom threshold", () => {
  const messages = [
    { id: "m1", role: "assistant", text: "a1" },
    { id: "m2", role: "assistant", text: "a2" },
    { id: "m3", role: "assistant", text: "a3" },
  ];

  const result = computeBubbleSequenceIndices(messages, 2);
  assert.equal(result.get("m1"), 1);
  assert.equal(result.get("m2"), 2);
  assert.equal(result.get("m3"), 3);
});

test("formatBubbleTime - formats ISO string to HH:MM:SS", () => {
  const formatted = formatBubbleTime("2026-11-10T14:32:05.123Z");
  assert.match(formatted, /\d{1,2}:\d{2}:\d{2}/);
});

test("formatBubbleTime - invalid timestamp returns empty string", () => {
  assert.equal(formatBubbleTime("not-a-date"), "");
  assert.equal(formatBubbleTime(undefined), "");
  assert.equal(formatBubbleTime(null), "");
});

test("formatFullDate - returns readable full date with ISO string", () => {
  const formatted = formatFullDate("2026-11-10T14:32:05.123Z");
  assert.ok(formatted.includes("2026-11-10T14:32:05.123Z"));
});
