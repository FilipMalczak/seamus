/**
 * Component tests for `Sidebar` — the navigation tree.
 *
 * These drive the real production component (loaded from `ui/src` via
 * esbuild) inside a jsdom document, so the interactional contracts can be
 * observed: inline renaming, the accept button, and the session status icon.
 *
 * They cover:
 *   - REQ-011 / INV-013 — inline tree node renaming and session status visibility
 *   - INV-010          — entity display name fallback to the full UUID
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
let Sidebar;

const CONFIG = {
  inference: { format: "steerable", base_url: "https://example.test", model_name: "m" },
};

const AGENT_ID = "11111111-1111-4111-8111-111111111111";
const SESSION_ID = "22222222-2222-4222-8222-222222222222";
const THREAD_ID = "33333333-3333-4333-8333-333333333333";

function thread(overrides = {}) {
  return {
    id: THREAD_ID,
    name: null,
    created_at: "2026-01-01T00:00:00Z",
    last_touched_at: "2026-01-01T00:00:00Z",
    is_open: true,
    status: "AWAITING_USER",
    mode: "chat",
    phase: null,
    ...overrides,
  };
}

function session(overrides = {}) {
  return {
    id: SESSION_ID,
    agent_id: AGENT_ID,
    name: null,
    created_at: "2026-01-01T00:00:00Z",
    last_touched_at: "2026-01-01T00:00:00Z",
    config: CONFIG,
    status: "ACTIVE",
    threads: [thread()],
    ...overrides,
  };
}

function agent(overrides = {}) {
  return {
    id: AGENT_ID,
    name: null,
    created_at: "2026-01-01T00:00:00Z",
    last_touched_at: "2026-01-01T00:00:00Z",
    config: CONFIG,
    sessionsMap: { [SESSION_ID]: session() },
    ...overrides,
  };
}

/**
 * Render the sidebar with the given agents and selection.
 *
 * @param {object} options Render options.
 * @returns {Promise<object>} The render handle plus the recorded callbacks.
 */
async function renderSidebar(options = {}) {
  const calls = {
    updateAgentName: [],
    updateSessionName: [],
    updateThreadName: [],
    createAgent: [],
    createSession: [],
    selectAgent: [],
    selectSession: [],
    selectThread: [],
  };

  const handle = await renderComponent(
    React.createElement(Sidebar, {
      agents: options.agents ?? [agent()],
      selectedAgentId: options.selectedAgentId ?? AGENT_ID,
      selectedSessionId: options.selectedSessionId ?? SESSION_ID,
      selectedThreadId: options.selectedThreadId ?? null,
      activeStatus: options.activeStatus,
      systemInfo: options.systemInfo,
      onSelectAgent: (id) => calls.selectAgent.push(id),
      onSelectSession: (agentId, sessionId) =>
        calls.selectSession.push([agentId, sessionId]),
      onSelectThread: (agentId, sessionId, threadId) =>
        calls.selectThread.push([agentId, sessionId, threadId]),
      onCreateAgent: async (name) => {
        calls.createAgent.push(name);
      },
      onCreateSession: async (agentId, name) => {
        calls.createSession.push([agentId, name]);
      },
      onUpdateAgentName: async (agentId, newName) => {
        calls.updateAgentName.push([agentId, newName]);
      },
      onUpdateSessionName: async (agentId, sessionId, newName) => {
        calls.updateSessionName.push([agentId, sessionId, newName]);
      },
      onUpdateThreadName: async (agentId, sessionId, threadId, newName) => {
        calls.updateThreadName.push([agentId, sessionId, threadId, newName]);
      },
      onEditConfig: () => {},
    })
  );

  return { ...handle, calls };
}

/** Find a button by its `title` attribute. */
function buttonByTitle(container, title) {
  return container.querySelector(`button[title="${title}"]`);
}

before(async () => {
  cleanupDom = setupClientDom();
  React = (await import("react")).default;
  ({ Sidebar } = await loadModule("components/Sidebar.tsx"));
});

after(async () => {
  await cleanupModules();
  cleanupDom?.cleanup();
});

beforeEach(() => {
  // The tree must never open a browser modal prompt. Any call is a failure.
  globalThis.window.prompt = () => {
    throw new Error("Sidebar must not call window.prompt()");
  };
});

test("Sidebar renders the agent, session and thread nodes", async () => {
  const { container, unmount } = await renderSidebar({
    agents: [agent({ name: "my-agent" })],
  });

  assert.match(container.textContent, /my-agent/);
  assert.match(container.textContent, /Agent Tree/);
  assert.ok(container.querySelector(".tree-agent-node"));
  assert.ok(container.querySelector(".tree-session-node"));
  assert.ok(container.querySelector(".tree-thread-node"));

  await unmount();
});

test("INV-010: an unnamed agent falls back to its full UUID", async () => {
  const { container, unmount } = await renderSidebar({
    agents: [agent({ name: null })],
  });

  const label = container.querySelector(".tree-agent-node .node-label");
  assert.equal(label.textContent, AGENT_ID);
  assert.equal(label.getAttribute("title"), `Agent: ${AGENT_ID}`);

  await unmount();
});

test("INV-010: an unnamed session falls back to its full UUID", async () => {
  const { container, unmount } = await renderSidebar();

  const label = container.querySelector(".tree-session-node .node-label");
  assert.equal(label.textContent, SESSION_ID);

  await unmount();
});

test("INV-010: an unnamed thread falls back to its full UUID", async () => {
  const { container, unmount } = await renderSidebar();

  const label = container.querySelector(".tree-thread-node .thread-name");
  assert.equal(label.textContent, THREAD_ID);

  await unmount();
});

test("INV-010: a blank name is treated as unnamed", async () => {
  const { container, unmount } = await renderSidebar({
    agents: [agent({ name: "   " })],
  });

  const label = container.querySelector(".tree-agent-node .node-label");
  assert.equal(label.textContent, AGENT_ID);

  await unmount();
});

test("REQ-011: clicking edit turns the agent label into an inline input", async () => {
  const { container, unmount } = await renderSidebar({
    agents: [agent({ name: "my-agent" })],
  });

  assert.equal(container.querySelector(".tree-agent-node .inline-edit-input"), null);

  await click(buttonByTitle(container, "Edit Agent Name"));

  const input = container.querySelector(".tree-agent-node .inline-edit-input");
  assert.ok(input, "expected an inline edit input");
  assert.equal(input.value, "my-agent");
  assert.equal(input.getAttribute("placeholder"), AGENT_ID);

  await unmount();
});

test("REQ-011: the edit button becomes a tick-box accept button", async () => {
  const { container, unmount } = await renderSidebar({
    agents: [agent({ name: "my-agent" })],
  });

  await click(buttonByTitle(container, "Edit Agent Name"));

  const accept = buttonByTitle(container, "Accept Name");
  assert.ok(accept, "expected the accept button");
  assert.ok(
    accept.querySelector("svg.lucide-check"),
    "expected the accept button to render a Check icon"
  );

  await unmount();
});

test("REQ-011: accepting a new agent name calls the rename handler", async () => {
  const { container, unmount, calls } = await renderSidebar({
    agents: [agent({ name: "my-agent" })],
  });

  await click(buttonByTitle(container, "Edit Agent Name"));
  const input = container.querySelector(".tree-agent-node .inline-edit-input");
  await type(input, "  renamed-agent  ");
  await click(buttonByTitle(container, "Accept Name"));

  assert.deepEqual(calls.updateAgentName, [[AGENT_ID, "renamed-agent"]]);
  assert.equal(container.querySelector(".tree-agent-node .inline-edit-input"), null);

  await unmount();
});

test("REQ-011: clearing the name passes null to the rename handler", async () => {
  const { container, unmount, calls } = await renderSidebar({
    agents: [agent({ name: "my-agent" })],
  });

  await click(buttonByTitle(container, "Edit Agent Name"));
  const input = container.querySelector(".tree-agent-node .inline-edit-input");
  await type(input, "   ");
  await click(buttonByTitle(container, "Accept Name"));

  assert.deepEqual(calls.updateAgentName, [[AGENT_ID, null]]);

  await unmount();
});

test("REQ-011: Enter accepts the inline edit", async () => {
  const { container, unmount, calls } = await renderSidebar({
    agents: [agent({ name: "my-agent" })],
  });

  await click(buttonByTitle(container, "Edit Agent Name"));
  const input = container.querySelector(".tree-agent-node .inline-edit-input");
  await type(input, "keyboard-agent");
  await pressKey(input, "Enter");

  assert.deepEqual(calls.updateAgentName, [[AGENT_ID, "keyboard-agent"]]);

  await unmount();
});

test("REQ-011: Escape cancels the inline edit without renaming", async () => {
  const { container, unmount, calls } = await renderSidebar({
    agents: [agent({ name: "my-agent" })],
  });

  await click(buttonByTitle(container, "Edit Agent Name"));
  const input = container.querySelector(".tree-agent-node .inline-edit-input");
  await type(input, "discarded");
  await pressKey(input, "Escape");

  assert.deepEqual(calls.updateAgentName, []);
  assert.equal(container.querySelector(".tree-agent-node .inline-edit-input"), null);
  assert.match(container.textContent, /my-agent/);

  await unmount();
});

test("REQ-011: sessions and threads are renamed inline as well", async () => {
  const { container, unmount, calls } = await renderSidebar();

  await click(buttonByTitle(container, "Edit Session Name"));
  const sessionInput = container.querySelector(".tree-session-node .inline-edit-input");
  assert.ok(sessionInput, "expected a session inline edit input");
  await type(sessionInput, "session-renamed");
  await click(buttonByTitle(container, "Accept Name"));
  assert.deepEqual(calls.updateSessionName, [
    [AGENT_ID, SESSION_ID, "session-renamed"],
  ]);

  await click(buttonByTitle(container, "Edit Thread Name"));
  const threadInput = container.querySelector(".tree-thread-node .inline-edit-input");
  assert.ok(threadInput, "expected a thread inline edit input");
  await type(threadInput, "thread-renamed");
  await click(buttonByTitle(container, "Accept Name"));
  assert.deepEqual(calls.updateThreadName, [
    [AGENT_ID, SESSION_ID, THREAD_ID, "thread-renamed"],
  ]);

  await unmount();
});

test("REQ-011: renaming never opens a browser prompt dialog", async () => {
  const { container, unmount } = await renderSidebar({
    agents: [agent({ name: "my-agent" })],
  });

  // `window.prompt` throws in the beforeEach hook; reaching this point means
  // no modal dialog was opened during the whole rename interaction.
  await click(buttonByTitle(container, "Edit Agent Name"));
  await click(buttonByTitle(container, "Accept Name"));

  await unmount();
});

test("INV-013: the session node surfaces the open thread status", async () => {
  const { container, unmount } = await renderSidebar({
    agents: [
      agent({
        sessionsMap: {
          [SESSION_ID]: session({
            threads: [thread({ status: "AWAITING_LLM" })],
          }),
        },
      }),
    ],
  });

  const badge = container.querySelector(".tree-session-node .session-status-badge");
  assert.ok(badge);
  assert.match(badge.getAttribute("class"), /status-awaiting-llm/);
  assert.equal(badge.getAttribute("title"), "Session Status: Thinking...");
  assert.ok(badge.querySelector("svg.status-icon-thinking"));

  await unmount();
});

test("INV-013: each operational status renders its own icon", async () => {
  const cases = [
    ["AWAITING_USER", "status-awaiting-user", "status-icon-ready", "Ready"],
    ["AWAITING_LLM", "status-awaiting-llm", "status-icon-thinking", "Thinking..."],
    ["EXECUTING_TOOL", "status-executing-tool", "status-icon-tool", "Executing Tool..."],
    ["ERROR", "status-error", "status-icon-error", "Error"],
  ];

  for (const [status, cssClass, iconClass, label] of cases) {
    const { container, unmount } = await renderSidebar({
      agents: [
        agent({
          sessionsMap: {
            [SESSION_ID]: session({ threads: [thread({ status })] }),
          },
        }),
      ],
    });

    const badge = container.querySelector(".tree-session-node .session-status-badge");
    assert.match(badge.getAttribute("class"), new RegExp(cssClass));
    assert.ok(badge.querySelector(`svg.${iconClass}`), `expected ${iconClass}`);
    assert.equal(badge.getAttribute("title"), `Session Status: ${label}`);

    await unmount();
  }
});

test("INV-013: a killed session overrides the thread status icon", async () => {
  const { container, unmount } = await renderSidebar({
    agents: [
      agent({
        sessionsMap: {
          [SESSION_ID]: session({
            status: "KILLED",
            threads: [thread({ status: "AWAITING_USER" })],
          }),
        },
      }),
    ],
  });

  const badge = container.querySelector(".tree-session-node .session-status-badge");
  assert.match(badge.getAttribute("class"), /status-killed/);
  assert.equal(badge.getAttribute("title"), "Session Status: Killed");

  await unmount();
});

test("INV-013: a failed session overrides the thread status icon", async () => {
  const { container, unmount } = await renderSidebar({
    agents: [
      agent({
        sessionsMap: {
          [SESSION_ID]: session({
            status: "FAILED",
            threads: [thread({ status: "AWAITING_USER" })],
          }),
        },
      }),
    ],
  });

  const badge = container.querySelector(".tree-session-node .session-status-badge");
  assert.match(badge.getAttribute("class"), /status-failed/);
  assert.equal(badge.getAttribute("title"), "Session Status: Failed");

  await unmount();
});

test("the active status overrides the stored thread status for the selected session", async () => {
  const { container, unmount } = await renderSidebar({
    activeStatus: "EXECUTING_TOOL",
  });

  const badge = container.querySelector(".tree-session-node .session-status-badge");
  assert.match(badge.getAttribute("class"), /status-executing-tool/);

  await unmount();
});

test("the thread node shows its open/closed state and mode badge", async () => {
  const { container, unmount } = await renderSidebar({
    agents: [
      agent({
        sessionsMap: {
          [SESSION_ID]: session({
            threads: [
              thread({ is_open: false, mode: "plan", phase: "discuss" }),
            ],
          }),
        },
      }),
    ],
  });

  assert.match(container.textContent, /Closed/);
  assert.match(container.textContent, /plan\/discuss/);
  assert.ok(container.querySelector(".thread-dot.dot-closed"));

  await unmount();
});

test("creating an agent and a session never prompts for a name", async () => {
  const { container, unmount, calls } = await renderSidebar();

  await click(container.querySelector(".btn-create-agent"));
  await click(buttonByTitle(container, "New Session"));

  assert.deepEqual(calls.createAgent, [null]);
  assert.deepEqual(calls.createSession, [[AGENT_ID, null]]);

  await unmount();
});

test("the empty state offers a first-agent creation button", async () => {
  const { container, unmount, calls } = await renderSidebar({ agents: [] });

  assert.match(container.textContent, /No agents created yet/);
  await click(container.querySelector(".tree-empty button"));
  assert.deepEqual(calls.createAgent, [null]);

  await unmount();
});

test("selecting a thread reports the full agent/session/thread triple", async () => {
  const { container, unmount, calls } = await renderSidebar();

  await click(container.querySelector(".tree-thread-node .thread-left-btn"));

  assert.deepEqual(calls.selectThread, [[AGENT_ID, SESSION_ID, THREAD_ID]]);

  await unmount();
});
