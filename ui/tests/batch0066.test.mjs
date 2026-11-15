import assert from "node:assert/strict";
import test, { after, before, beforeEach } from "node:test";

import { click, renderComponent, setupClientDom } from "./helpers/clientDom.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let cleanupDom;
let React;
let MessageItem;
let useInteractionNotifications;

before(async () => {
  ({ cleanup: cleanupDom } = setupClientDom());
  React = (await import("react")).default;
  ({ MessageItem } = await loadModule("components/MessageItem.tsx"));
  ({ useInteractionNotifications } = await loadModule(
    "hooks/useInteractionNotifications.ts"
  ));
});

after(() => {
  cleanupModules();
  cleanupDom?.();
});

beforeEach(() => {
  document.title = "Seamus";
});

test("MessageItem renders conversational anchor chip for tabbed artifact and opens it on click", async () => {
  let opened = null;
  const msg = {
    id: "assistant-1",
    role: "assistant",
    text: "",
    timestamp: "2026-01-15T10:20:30.000Z",
    parts: [
      {
        type: "tool_call",
        id: "tc-1",
        toolCall: {
          id: "call-1",
          name: "make_plan",
          args: {},
          result: '{"plan_id": "plan-1"}',
          status: "completed",
        },
      },
    ],
  };

  const sessionArtifacts = [
    {
      kind: "plans",
      name: "plan-1",
      title: "My Plan",
      is_closed: false,
      manifest: { exposition: "tabbed", blocking: false, title: "My Plan" },
    },
  ];

  const view = await renderComponent(
    React.createElement(MessageItem, {
      message: msg,
      sessionArtifacts,
      onOpenArtifactTab: (kind, name) => {
        opened = { kind, name };
      },
    })
  );

  const chip = view.container.querySelector(".artifact-anchor-chip");
  assert.ok(chip, "expected conversational anchor chip");
  assert.match(chip.textContent || "", /Open Plan: My Plan/);

  await click(chip);
  assert.deepEqual(opened, { kind: "plans", name: "plan-1" });
});

test("useInteractionNotifications updates document.title when hidden and awaiting user", async () => {
  const originalHidden = Object.getOwnPropertyDescriptor(document, "hidden");
  Object.defineProperty(document, "hidden", { configurable: true, get: () => true });

  try {
    function Probe({ status, blocking }) {
      useInteractionNotifications({
        status,
        hasOpenBlockingArtifact: blocking,
        sessionName: "demo",
      });
      return null;
    }

    const view = await renderComponent(
      React.createElement(Probe, { status: "AWAITING_LLM", blocking: false })
    );
    await view.rerender(React.createElement(Probe, { status: "AWAITING_USER", blocking: false }));
    await new Promise((resolve) => setTimeout(resolve, 0));

    assert.match(document.title, /Action Needed/);
  } finally {
    if (originalHidden) {
      Object.defineProperty(document, "hidden", originalHidden);
    }
  }
});
