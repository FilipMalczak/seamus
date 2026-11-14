/**
 * Component tests for `MessageItem` and its branching affordances.
 *
 * These tests render the real production components (loaded from `ui/src`
 * via esbuild) to static markup and assert on the observable output:
 * branch action buttons, provenance separators, tool-group indicators,
 * sequence indices, and bubble timestamps.
 *
 * They cover the UI half of the granular bidirectional branching contract
 * described in `decisions/0054-granular-bidirectional-session-branching.md`
 * and the technical-debt entry "Rigorous and Detailed Automated Testing
 * Matrix for Granular Bidirectional Session Branching" in
 * `knowledge/backlog.md`.
 */

import assert from "node:assert/strict";
import test, { after, before } from "node:test";

import { installDomShim } from "./helpers/domShim.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let restoreDom;
let React;
let renderToStaticMarkup;
let MessageItem;
let BubbleBranchActions;
let BranchProvenanceSeparator;
let ToolGroupProvenanceIndicator;
let SyntheticMessageBlock;
let ReasoningBlock;

before(async () => {
  restoreDom = installDomShim();
  React = (await import("react")).default;
  ({ renderToStaticMarkup } = await import("react-dom/server"));

  const mod = await loadModule("components/MessageItem.tsx");
  MessageItem = mod.MessageItem;
  BubbleBranchActions = mod.BubbleBranchActions;
  BranchProvenanceSeparator = mod.BranchProvenanceSeparator;
  ToolGroupProvenanceIndicator = mod.ToolGroupProvenanceIndicator;
  SyntheticMessageBlock = mod.SyntheticMessageBlock;
  ReasoningBlock = mod.ReasoningBlock;
});

after(async () => {
  await cleanupModules();
  restoreDom?.();
});

/** Lazily resolve `React.createElement` — React is loaded in the `before` hook. */
function h(...args) {
  return React.createElement(...args);
}

function render(element) {
  return renderToStaticMarkup(element);
}

function baseMessage(overrides = {}) {
  return {
    id: "msg-1",
    role: "assistant",
    text: "",
    timestamp: "2026-01-02T03:04:05.000Z",
    ...overrides,
  };
}

function provenance(overrides = {}) {
  return {
    parent_session_id: "parent-session-abcdef123456",
    parent_message_id: "msg-1",
    parent_session_name: "Parent Session",
    branched_at: "2026-01-02T03:04:05.000Z",
    branch_position: "after",
    ...overrides,
  };
}

test("BubbleBranchActions renders nothing without an onBranch handler", () => {
  const markup = render(
    h(BubbleBranchActions, { targetId: "msg-1", itemType: "bot_message" })
  );
  assert.equal(markup, "");
});

test("BubbleBranchActions renders both before and after buttons by default", () => {
  const markup = render(
    h(BubbleBranchActions, {
      targetId: "msg-1",
      itemType: "bot_message",
      onBranch: () => {},
    })
  );
  assert.match(markup, /branch-before-btn/);
  assert.match(markup, /branch-after-btn/);
  assert.match(markup, /branch-dir-right/);
});

test("BubbleBranchActions honours onlyPosition=before", () => {
  const markup = render(
    h(BubbleBranchActions, {
      targetId: "msg-1",
      itemType: "bot_message",
      onBranch: () => {},
      onlyPosition: "before",
    })
  );
  assert.match(markup, /branch-before-btn/);
  assert.doesNotMatch(markup, /branch-after-btn/);
  assert.match(markup, /branch-only-before/);
});

test("BubbleBranchActions honours onlyPosition=after", () => {
  const markup = render(
    h(BubbleBranchActions, {
      targetId: "msg-1",
      itemType: "bot_message",
      onBranch: () => {},
      onlyPosition: "after",
    })
  );
  assert.doesNotMatch(markup, /branch-before-btn/);
  assert.match(markup, /branch-after-btn/);
  assert.match(markup, /branch-only-after/);
});

test("BubbleBranchActions distinguishes tool group from single tool call", () => {
  const groupMarkup = render(
    h(BubbleBranchActions, {
      targetId: "call-1",
      itemType: "tool_call",
      isGroup: true,
      onBranch: () => {},
    })
  );
  assert.match(groupMarkup, /Branch before tool group/);
  assert.match(groupMarkup, /Branch after tool group/);

  const singleMarkup = render(
    h(BubbleBranchActions, {
      targetId: "call-1",
      itemType: "tool_call",
      onBranch: () => {},
    })
  );
  assert.match(singleMarkup, /Branch before tool execution/);
  assert.match(singleMarkup, /Branch after tool execution/);
});

test("BubbleBranchActions uses item-type specific tooltips", () => {
  const userMarkup = render(
    h(BubbleBranchActions, {
      targetId: "msg-1",
      itemType: "user_message",
      onBranch: () => {},
    })
  );
  assert.match(userMarkup, /get back to waiting for user input/);

  const thinkingMarkup = render(
    h(BubbleBranchActions, {
      targetId: "msg-1",
      itemType: "bot_thinking",
      onBranch: () => {},
    })
  );
  assert.match(thinkingMarkup, /re-generate reasoning/);
});

test("BranchProvenanceSeparator renders the branch position label", () => {
  for (const [position, label] of [
    ["before", "branched before"],
    ["after", "branched after"],
    [undefined, "branched from"],
  ]) {
    const markup = render(
      h(BranchProvenanceSeparator, {
        provenance: provenance({ branch_position: position }),
      })
    );
    assert.match(markup, new RegExp(label));
    assert.match(markup, /data-testid="branch-provenance-separator"/);
  }
});

test("BranchProvenanceSeparator prefers the commit sha over the session name", () => {
  const markup = render(
    h(BranchProvenanceSeparator, {
      provenance: provenance({ commit_sha: "abcdef1234567890" }),
    })
  );
  assert.match(markup, /abcdef12/);
  assert.doesNotMatch(markup, /Parent Session/);
});

test("BranchProvenanceSeparator renders a navigation button when a handler is given", () => {
  const markup = render(
    h(BranchProvenanceSeparator, {
      provenance: provenance(),
      onNavigateToSession: () => {},
    })
  );
  assert.match(markup, /separator-link-btn/);
  assert.match(markup, /Navigate to parent session/);
});

test("ToolGroupProvenanceIndicator renders the branch position and target", () => {
  const markup = render(
    h(ToolGroupProvenanceIndicator, {
      provenance: provenance({ branch_position: "before" }),
    })
  );
  assert.match(markup, /data-testid="tool-group-indicator-row"/);
  assert.match(markup, /branched before/);
  assert.match(markup, /Parent Session/);
});

test("MessageItem renders a user bubble with its text", () => {
  const markup = render(
    h(MessageItem, {
      message: baseMessage({ id: "u-1", role: "user", text: "hello there" }),
    })
  );
  assert.match(markup, /hello there/);
  assert.match(markup, /message-row/);
});

test("MessageItem renders the bubble timestamp and full-date tooltip", () => {
  const markup = render(
    h(MessageItem, {
      message: baseMessage({ id: "u-1", role: "user", text: "hi" }),
    })
  );
  assert.match(markup, /bubble-timestamp/);
  assert.match(markup, /2026-01-02T03:04:05\.000Z/);
});

test("MessageItem renders a sequence index badge when one is supplied", () => {
  const markup = render(
    h(MessageItem, {
      message: baseMessage({ id: "u-1", role: "user", text: "hi" }),
      sequenceIndex: 3,
    })
  );
  assert.match(markup, /bubble-sequence-badge/);
  assert.match(markup, /Step #3 in sequence/);
  assert.match(markup, />#3</);
});

test("MessageItem resolves per-part sequence indices from the map", () => {
  const markup = render(
    h(MessageItem, {
      message: baseMessage({
        id: "a-1",
        parts: [
          { type: "text", id: "p-text", content: "answer" },
          { type: "reasoning", id: "p-reason", content: "thinking" },
        ],
      }),
      sequenceIndices: new Map([
        ["p-text", 7],
        ["p-reason", 8],
      ]),
    })
  );
  assert.match(markup, /Step #7 in sequence/);
  assert.match(markup, /Step #8 in sequence/);
});

test("MessageItem renders branch actions for a user message", () => {
  const markup = render(
    h(MessageItem, {
      message: baseMessage({ id: "u-1", role: "user", text: "hi" }),
      onBranch: () => {},
    })
  );
  assert.match(markup, /bubble-branch-actions/);
  assert.match(markup, /branch-before-btn/);
  assert.match(markup, /branch-after-btn/);
});

test("MessageItem renders a provenance separator for a matching parent message", () => {
  const markup = render(
    h(MessageItem, {
      message: baseMessage({ id: "msg-1", role: "user", text: "hi" }),
      provenanceList: [provenance({ parent_message_id: "msg-1" })],
    })
  );
  assert.match(markup, /data-testid="branch-provenance-separator"/);
});

test("MessageItem does not render a separator for an unrelated parent message", () => {
  const markup = render(
    h(MessageItem, {
      message: baseMessage({ id: "msg-1", role: "user", text: "hi" }),
      provenanceList: [provenance({ parent_message_id: "some-other-id" })],
    })
  );
  assert.doesNotMatch(markup, /data-testid="branch-provenance-separator"/);
});

test("MessageItem renders a synthetic message block for synthetic markers", () => {
  const markup = render(
    h(MessageItem, {
      message: baseMessage({
        id: "s-1",
        role: "user",
        text: "<SYNTHETIC MESSAGE INDICATOR> please continue",
      }),
    })
  );
  assert.match(markup, /synthetic-message/);
});

test("MessageItem renders tool call parts with their tool name", () => {
  const markup = render(
    h(MessageItem, {
      message: baseMessage({
        id: "a-1",
        parts: [
          {
            type: "tool_call",
            id: "p-call",
            toolCall: {
              id: "call-1",
              name: "read_file",
              args: { path: "/workspace/a.txt" },
              status: "success",
            },
          },
        ],
      }),
    })
  );
  assert.match(markup, /read_file/);
});

test("MessageItem renders a collapsed reasoning card for reasoning parts", () => {
  const markup = render(
    h(MessageItem, {
      message: baseMessage({
        id: "a-1",
        parts: [
          { type: "reasoning", id: "p-reason", content: "considering options" },
        ],
      }),
    })
  );
  assert.match(markup, /reasoning-card/);
  assert.match(markup, /Thought process/);
  // The reasoning body is collapsed behind a toggle, so it is not in the
  // server-rendered markup.
  assert.doesNotMatch(markup, /considering options/);
});

test("SyntheticMessageBlock renders the event badge and a summary", () => {
  const markup = render(
    h(SyntheticMessageBlock, { text: "<SYNTHETIC MESSAGE INDICATOR> go on" })
  );
  assert.match(markup, /synthetic-message-card/);
  assert.match(markup, /synthetic-badge/);
  // The marker prefix is stripped from the summary shown to the user.
  assert.match(markup, /go on/);
  assert.doesNotMatch(markup, /SYNTHETIC MESSAGE INDICATOR/);
});

test("ReasoningBlock renders a collapsed card with a timestamp when present", () => {
  const markup = render(
    h(ReasoningBlock, {
      content: "deep thought",
      timestamp: "2026-01-02T03:04:05.000Z",
    })
  );
  assert.match(markup, /reasoning-card/);
  assert.match(markup, /Thought process/);
  assert.match(markup, /part-timestamp/);
  assert.match(markup, /2026-01-02T03:04:05\.000Z/);
});
