import assert from "node:assert/strict";
import test from "node:test";
import {
  buildToolCallDrafts,
  parseSteerableQueueFile,
  parseToolCallDraft,
  planSteerableUpload,
  serializeSteerableQueue,
  steerableQueueFilename,
  STEERABLE_UPLOAD_MODE_LABELS,
  STEERABLE_UPLOAD_MODES,
} from "../src/utils/steerable.ts";

test("parseToolCallDraft - untouched draft yields no call and no error", () => {
  const result = parseToolCallDraft({ id: "1", name: "", args: "{}" });
  assert.equal(result.call, null);
  assert.equal(result.error, null);
});

test("parseToolCallDraft - name only yields empty args", () => {
  const result = parseToolCallDraft({ id: "1", name: "ls", args: "" });
  assert.deepEqual(result.call, { name: "ls", args: {} });
  assert.equal(result.error, null);
});

test("parseToolCallDraft - parses JSON object args", () => {
  const result = parseToolCallDraft({
    id: "1",
    name: "write_file",
    args: '{"path": "/a.txt", "content": "hi"}',
  });
  assert.deepEqual(result.call, {
    name: "write_file",
    args: { path: "/a.txt", content: "hi" },
  });
});

test("parseToolCallDraft - malformed JSON is reported as an error", () => {
  const result = parseToolCallDraft({ id: "1", name: "ls", args: "{oops" });
  assert.equal(result.call, null);
  assert.equal(result.error, "Tool arguments must be valid JSON.");
});

test("parseToolCallDraft - non-object JSON args are rejected", () => {
  const result = parseToolCallDraft({ id: "1", name: "ls", args: "[1, 2]" });
  assert.equal(result.call, null);
  assert.equal(result.error, "Tool arguments must be a JSON object.");
});

test("parseToolCallDraft - a name is required once a draft is filled in", () => {
  const result = parseToolCallDraft({ id: "1", name: "", args: '{"a": 1}' });
  assert.equal(result.call, null);
  assert.equal(result.error, "Tool name is required.");
});

test("buildToolCallDrafts - collects multiple tool calls in draft order", () => {
  const result = buildToolCallDrafts([
    { id: "1", name: "ls", args: '{"path": "/"}' },
    { id: "2", name: "read_file", args: '{"path": "/a.txt"}' },
  ]);
  assert.equal(result.invalid, false);
  assert.equal(result.error, null);
  assert.equal(result.calls.length, 2);
  assert.equal(result.calls[0].name, "ls");
  assert.equal(result.calls[1].name, "read_file");
  assert.deepEqual(result.calls[1].args, { path: "/a.txt" });
});

test("buildToolCallDrafts - skips untouched drafts", () => {
  const result = buildToolCallDrafts([
    { id: "1", name: "", args: "{}" },
    { id: "2", name: "ls", args: "{}" },
  ]);
  assert.equal(result.invalid, false);
  assert.equal(result.calls.length, 1);
  assert.equal(result.calls[0].name, "ls");
});

test("buildToolCallDrafts - one invalid draft invalidates the whole batch", () => {
  const result = buildToolCallDrafts([
    { id: "1", name: "ls", args: "{}" },
    { id: "2", name: "read_file", args: "{bad" },
  ]);
  assert.equal(result.invalid, true);
  assert.equal(result.calls.length, 0);
  assert.equal(result.error, "Tool arguments must be valid JSON.");
});

test("serializeSteerableQueue - writes an envelope with the responses", () => {
  const json = serializeSteerableQueue(
    "session:s1:agent",
    [{ text: "hello", reasoning: null, tool_calls: [] }],
    "wait",
    "2026-01-01T00:00:00.000Z"
  );
  const parsed = JSON.parse(json);
  assert.equal(parsed.instance_id, "session:s1:agent");
  assert.equal(parsed.strategy, "wait");
  assert.equal(parsed.exported_at, "2026-01-01T00:00:00.000Z");
  assert.equal(parsed.responses.length, 1);
  assert.equal(parsed.responses[0].text, "hello");
});

test("serializeSteerableQueue - round trips through parseSteerableQueueFile", () => {
  const responses = [
    {
      text: "working",
      reasoning: "thinking",
      tool_calls: [
        { name: "ls", args: { path: "/" } },
        { name: "read_file", args: { path: "/a.txt" } },
      ],
    },
    { text: "done", reasoning: null, tool_calls: [] },
  ];
  const json = serializeSteerableQueue("session:s1:agent", responses, "wait");
  const parsed = parseSteerableQueueFile(json);
  assert.equal(parsed.ok, true);
  assert.deepEqual(parsed.responses, responses);
});

test("parseSteerableQueueFile - accepts a bare list of responses", () => {
  const parsed = parseSteerableQueueFile(
    JSON.stringify([{ text: "one" }, { text: "two" }])
  );
  assert.equal(parsed.ok, true);
  assert.equal(parsed.responses.length, 2);
  assert.equal(parsed.responses[1].text, "two");
  assert.deepEqual(parsed.responses[0].tool_calls, []);
});

test("parseSteerableQueueFile - rejects invalid JSON", () => {
  const parsed = parseSteerableQueueFile("{not json");
  assert.equal(parsed.ok, false);
  assert.equal(parsed.error, "The file is not valid JSON.");
});

test("parseSteerableQueueFile - rejects a file without responses", () => {
  const parsed = parseSteerableQueueFile(JSON.stringify({ foo: "bar" }));
  assert.equal(parsed.ok, false);
  assert.match(parsed.error, /responses/);
});

test("parseSteerableQueueFile - rejects a non-list responses field", () => {
  const parsed = parseSteerableQueueFile(JSON.stringify({ responses: "nope" }));
  assert.equal(parsed.ok, false);
  assert.equal(parsed.error, 'The "responses" field must be a list.');
});

test("parseSteerableQueueFile - rejects a tool call without a name", () => {
  const parsed = parseSteerableQueueFile(
    JSON.stringify([{ text: "x", tool_calls: [{ args: {} }] }])
  );
  assert.equal(parsed.ok, false);
  assert.match(parsed.error, /missing a name/);
});

test("parseSteerableQueueFile - rejects non-object tool call arguments", () => {
  const parsed = parseSteerableQueueFile(
    JSON.stringify([{ text: "x", tool_calls: [{ name: "ls", args: [1] }] }])
  );
  assert.equal(parsed.ok, false);
  assert.match(parsed.error, /non-object arguments/);
});

test("parseSteerableQueueFile - rejects a non-string text field", () => {
  const parsed = parseSteerableQueueFile(JSON.stringify([{ text: 42 }]));
  assert.equal(parsed.ok, false);
  assert.match(parsed.error, /non-string "text"/);
});

test("steerableQueueFilename - sanitizes the instance id", () => {
  assert.equal(
    steerableQueueFilename("session:abc:agent"),
    "steerable-queue-session-abc-agent.json"
  );
});

test("STEERABLE_UPLOAD_MODES - offers replace and extend", () => {
  assert.deepEqual(STEERABLE_UPLOAD_MODES, ["replace", "extend"]);
  assert.equal(STEERABLE_UPLOAD_MODE_LABELS.replace, "Replace");
  assert.equal(STEERABLE_UPLOAD_MODE_LABELS.extend, "Extend");
});

test("planSteerableUpload - replace swaps the whole queue", () => {
  const plan = planSteerableUpload("replace", [{ text: "one" }]);
  assert.equal(plan.kind, "replace");
  assert.deepEqual(plan.responses, [{ text: "one" }]);
});

test("planSteerableUpload - extend appends to the existing queue", () => {
  const plan = planSteerableUpload("extend", [{ text: "two" }]);
  assert.equal(plan.kind, "append");
  assert.deepEqual(plan.responses, [{ text: "two" }]);
});

test("planSteerableUpload - an empty upload is still a valid plan", () => {
  assert.equal(planSteerableUpload("replace", []).kind, "replace");
  assert.equal(planSteerableUpload("extend", []).kind, "append");
  assert.deepEqual(planSteerableUpload("extend", []).responses, []);
});
