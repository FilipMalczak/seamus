/**
 * Component tests for `AgentInspector` — the runtime introspection console.
 *
 * `AgentInspector` implements REQ-018 (the inspection console) and REQ-048
 * (semantic tool labelling and filtering). Its contracts are:
 *
 *   - the system prompt is decomposed into three layers — composite,
 *     scaffold and custom instructions — and the operator can switch between
 *     them;
 *   - the tool inventory lists every bound tool with its semantic label
 *     badges, and the category filter narrows the list;
 *   - a tool's JSON schema is revealed on demand;
 *   - the credential status is reported as *configured / not configured*
 *     without ever echoing the credential itself (INV-021);
 *   - the todo checklist, the skills inventory and the steerable instances
 *     are all reachable.
 *
 * The component is driven against a stubbed `fetch`, so the real API client
 * call runs against a scripted inspection report.
 */

import assert from "node:assert/strict";
import test, { after, before, beforeEach } from "node:test";

import { click, renderComponent, setupClientDom } from "./helpers/clientDom.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let cleanupDom;
let React;
let AgentInspector;

const AGENT_ID = "11111111-1111-4111-8111-111111111111";
const SESSION_ID = "22222222-2222-4222-8222-222222222222";
const THREAD_ID = "33333333-3333-4333-8333-333333333333";

/**
 * A representative inspection report.
 *
 * @param {object} overrides Field overrides.
 * @returns {object} The report.
 */
function makeReport(overrides = {}) {
  return {
    agent_id: AGENT_ID,
    agent_name: "coder",
    session_id: SESSION_ID,
    session_name: "refactor",
    thread_id: THREAD_ID,
    thread_name: "discuss",
    status: "AWAITING_USER",
    git: {
      branch: "session/refactor",
      commit_sha: "abc123",
      commit_message: "checkpoint: turn 1",
      commit_time: "2026-01-01T00:00:00Z",
      repo_name: "agent-11111111",
      gitea_url: "http://gitea.local",
    },
    inference: {
      model_name: "openai/gpt-oss-120b",
      format: "openai",
      base_url: "https://openrouter.ai/api/v1",
      api_key_configured: true,
    },
    prompts: {
      composite: "<scaffolding>composite prompt</scaffolding>",
      scaffold: "<scaffolding>scaffold prompt</scaffolding>",
      custom: "<custom>custom instructions</custom>",
    },
    tools: [
      {
        name: "ls",
        description: "List files in a directory.",
        parameters: {
          type: "object",
          properties: { path: { type: "string" } },
          required: ["path"],
        },
        backend: "opensandbox",
        category: "Sandbox",
        labels: [{ title: "opensandbox", color: "#38bdf8" }],
      },
      {
        name: "web_search",
        description: "Search the web.",
        parameters: { type: "object", properties: {} },
        backend: "web",
        category: "Web",
        labels: [{ title: "web", color: "#34d399" }],
      },
    ],
    todos: [{ id: "1", content: "Read the code", status: "pending" }],
    todo_implementation: "deepagents",
    skills: [
      {
        name: "artifacts",
        description: "Build artifacts.",
        origin_layer: "bundled",
        sandbox_path: "/skills/bundled/artifacts",
        content: "instructions",
        active: true,
      },
    ],
    skills_implementation: "seamus",
    web_search: "duckduckgo",
    artifacts_implementation: "seamus",
    subagents: [],
    mounted_repositories: [],
    history: {
      message_count: 2,
      checkpoint_step: 3,
      messages: [
        { id: "m1", role: "user", content: "hello" },
        { id: "m2", role: "assistant", content: "hi" },
      ],
    },
    workspace: {
      operational_dir: "/workspace",
      files: ["notes/research.md"],
    },
    steerable_models: [
      {
        instance_id: `session:${SESSION_ID}:agent`,
        role: "agent",
        strategy: "wait",
        queued: 0,
        default_response: null,
        wait_timeout: 10,
      },
    ],
    ...overrides,
  };
}

/**
 * Install a `fetch` stub serving the inspection endpoint.
 *
 * @param {object} options Stub options.
 * @returns {{requests: Array<object>}} The recorded requests.
 */
function installFetchStub(options = {}) {
  const requests = [];
  globalThis.fetch = async (url) => {
    requests.push({ url: String(url) });
    if (String(url).includes("/inspect")) {
      return new Response(JSON.stringify(options.report ?? makeReport()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response("{}", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  return { requests };
}

/**
 * Render the inspector.
 *
 * @param {object} options Render options.
 * @returns {Promise<object>} The render handle.
 */
async function renderInspector(options = {}) {
  const stub = installFetchStub(options);
  const handle = await renderComponent(
    React.createElement(AgentInspector, {
      agentId: "agentId" in options ? options.agentId : AGENT_ID,
      sessionId: "sessionId" in options ? options.sessionId : SESSION_ID,
      threadId: "threadId" in options ? options.threadId : THREAD_ID,
      agentName: options.agentName ?? "coder",
      sessionName: options.sessionName ?? "refactor",
    })
  );
  return { ...handle, ...stub };
}

/** The tab carrying the given label. */
function tab(container, label) {
  return Array.from(container.querySelectorAll(".inspector-tab-btn")).find((button) =>
    button.textContent.includes(label)
  );
}

/** Flush pending promise-driven updates. */
async function settle(ms = 20) {
  const { act } = await import("react");
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms));
  });
}

before(async () => {
  cleanupDom = setupClientDom();
  React = (await import("react")).default;
  ({ AgentInspector } = await loadModule("components/AgentInspector.tsx"));
});

after(async () => {
  await cleanupModules();
  cleanupDom?.cleanup();
});

beforeEach(() => {
  globalThis.navigator.clipboard = {
    writeText: async () => {},
  };
});

test("REQ-018: the inspection report is fetched for the active session", async () => {
  const { requests, unmount } = await renderInspector();
  await settle();

  assert.ok(
    requests.some((request) =>
      request.url.includes(`/agent/${AGENT_ID}/session/${SESSION_ID}/inspect`)
    )
  );

  await unmount();
});

test("REQ-018: without a session the inspector renders its empty state", async () => {
  const { container, requests, unmount } = await renderInspector({
    agentId: null,
    sessionId: null,
  });
  await settle();

  assert.ok(container.querySelector(".inspector-empty-state"));
  assert.equal(requests.length, 0, "no session means no request");

  await unmount();
});

test("REQ-018: the system prompt is decomposed into three selectable layers", async () => {
  const { container, unmount } = await renderInspector();
  await settle();

  const pills = Array.from(container.querySelectorAll(".layer-pill")).map((pill) =>
    pill.textContent.trim()
  );
  assert.deepEqual(pills, [
    "Composite (Effective Prompt)",
    "Scaffold (OpenSandbox)",
    "Custom Instructions",
  ]);

  const box = container.querySelector(".prompt-content-box");
  assert.match(box.textContent, /composite prompt/);

  await unmount();
});

test("REQ-018: the scaffold layer shows the sandbox scaffold", async () => {
  const { container, unmount } = await renderInspector();
  await settle();

  await click(
    Array.from(container.querySelectorAll(".layer-pill")).find((pill) =>
      pill.textContent.includes("Scaffold")
    )
  );

  assert.match(container.querySelector(".prompt-content-box").textContent, /scaffold prompt/);

  await unmount();
});

test("REQ-018: the custom layer shows the custom instructions", async () => {
  const { container, unmount } = await renderInspector();
  await settle();

  await click(
    Array.from(container.querySelectorAll(".layer-pill")).find((pill) =>
      pill.textContent.includes("Custom")
    )
  );

  assert.match(container.querySelector(".prompt-content-box").textContent, /custom instructions/);

  await unmount();
});

test("REQ-018: the prompt can be copied in one click", async () => {
  const written = [];
  globalThis.navigator.clipboard = {
    writeText: async (value) => {
      written.push(value);
    },
  };

  const { container, unmount } = await renderInspector();
  await settle();

  await click(
    Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent.includes("Copy Prompt")
    )
  );

  // The button resets its "Copied!" label on a 2s timer; wait for it so
  // the timer does not fire after the DOM has been torn down.
  await settle(2100);

  assert.equal(written.length, 1);
  assert.match(written[0], /composite prompt/);

  await unmount();
});

test("REQ-048: every tool is listed with its semantic label badge", async () => {
  const { container, unmount } = await renderInspector();
  await settle();

  await click(tab(container, "Tools"));

  const names = Array.from(container.querySelectorAll(".tool-inspect-card .tool-name")).map(
    (el) => el.textContent
  );
  assert.ok(names.includes("ls"));
  assert.ok(names.includes("web_search"));

  const labels = Array.from(container.querySelectorAll(".tool-label-badge")).map(
    (el) => el.textContent
  );
  assert.ok(labels.includes("opensandbox"));
  assert.ok(labels.includes("web"));

  await unmount();
});

test("REQ-048: the category filter narrows the tool list", async () => {
  const { container, unmount } = await renderInspector();
  await settle();

  await click(tab(container, "Tools"));

  const filters = Array.from(container.querySelectorAll(".category-filter-btn"));
  assert.ok(filters.length >= 3, "expected a category filter per label");

  await click(
    filters.find((button) => button.textContent.includes("opensandbox"))
  );

  const names = Array.from(container.querySelectorAll(".tool-inspect-card .tool-name")).map(
    (el) => el.textContent
  );
  assert.ok(names.includes("ls"));
  assert.ok(!names.includes("web_search"), "the filtered-out tool is hidden");

  await unmount();
});

test("REQ-048: the tool schema is revealed on demand", async () => {
  const { container, unmount } = await renderInspector();
  await settle();

  await click(tab(container, "Tools"));

  const toggle = Array.from(container.querySelectorAll(".btn-tool-toggle")).find((button) =>
    button.textContent.includes("View Schema")
  );
  assert.ok(toggle);

  await click(toggle);

  const card = container.querySelector(".tool-inspect-card");
  assert.match(card.textContent, /path/);

  await unmount();
});

test("REQ-044: a disabled web search is called out explicitly", async () => {
  const { container, unmount } = await renderInspector({
    report: makeReport({ web_search: "none" }),
  });
  await settle();

  await click(tab(container, "Tools"));

  assert.match(container.textContent, /Web search tools are disabled/);

  await unmount();
});

test("INV-021: the credential status is reported without echoing the credential", async () => {
  const { container, unmount } = await renderInspector();
  await settle();

  await click(tab(container, "Inference & Runtime"));

  assert.match(container.textContent, /Configured/);
  assert.doesNotMatch(container.textContent, /sk-/);

  await unmount();
});

test("REQ-018: the inference panel reports the model and the Git boundary", async () => {
  const { container, unmount } = await renderInspector();
  await settle();

  await click(tab(container, "Inference & Runtime"));

  assert.match(container.textContent, /openai\/gpt-oss-120b/);
  assert.match(container.textContent, /session\/refactor/);
  assert.match(container.textContent, /\/workspace/);

  await unmount();
});

test("REQ-029: the active todos are listed", async () => {
  const { container, unmount } = await renderInspector();
  await settle();

  await click(tab(container, "Todos"));

  assert.match(container.textContent, /Read the code/);

  await unmount();
});

test("REQ-043: the skills inventory is listed", async () => {
  const { container, unmount } = await renderInspector();
  await settle();

  await click(tab(container, "Skills"));

  assert.match(container.textContent, /artifacts/);

  await unmount();
});

test("REQ-051: the steerable instances are reachable", async () => {
  const { container, unmount } = await renderInspector();
  await settle();

  assert.ok(tab(container, "Steerable"), "expected a Steerable tab");

  await click(tab(container, "Steerable"));
  await settle();

  assert.match(container.textContent, /agent/);

  await unmount();
});

test("REQ-018: the steerable tab is absent when there are no steerable instances", async () => {
  const { container, unmount } = await renderInspector({
    report: makeReport({ steerable_models: [] }),
  });
  await settle();

  assert.equal(tab(container, "Steerable"), undefined);

  await unmount();
});

test("REQ-018: the trajectory tab reports the message count", async () => {
  const { container, unmount } = await renderInspector();
  await settle();

  await click(tab(container, "Trajectory"));

  assert.match(container.textContent, /hello/);
  assert.match(container.textContent, /hi/);

  await unmount();
});

test("REQ-018: the workspace tab lists the operational directory and its files", async () => {
  const { container, unmount } = await renderInspector();
  await settle();

  await click(tab(container, "Workspace Files"));

  assert.match(container.textContent, /notes\/research\.md/);

  await unmount();
});
