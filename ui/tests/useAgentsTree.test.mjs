/**
 * Hook tests for `useAgentsTree` — the navigation tree and URL state.
 *
 * `useAgentsTree` owns the tree hydration and the *URL state
 * synchronisation* required by REQ-032 / INV-039:
 *
 *   - the tree is loaded from the agent list, the agent details and the
 *     session details;
 *   - the initial selection is hydrated from the URL query parameters, and
 *     each entity may be addressed by its canonical UUID *or* by its
 *     human-readable slug (REQ-005);
 *   - without a URL hint, the most recently touched session is selected;
 *   - a browser Back / Forward navigation re-resolves the selection from the
 *     URL;
 *   - selecting an agent selects its most recent session and clears the
 *     thread selection.
 *
 * The hook is driven through a real DOM with a stubbed `fetch`, so the real
 * API client calls and the real URL parsing run against scripted responses.
 */

import assert from "node:assert/strict";
import test, { after, before, beforeEach } from "node:test";

import { renderComponent, setupClientDom } from "./helpers/clientDom.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let cleanupDom;
let React;
let useAgentsTree;
let window;

const AGENT_A = "aaaaaaaa-1111-4111-8111-111111111111";
const AGENT_B = "bbbbbbbb-2222-4222-8222-222222222222";
const SESSION_OLD = "11111111-3333-4333-8333-333333333333";
const SESSION_NEW = "22222222-4444-4444-8444-444444444444";
const THREAD_A = "aaaaaaaa-5555-4555-8555-555555555555";
const THREAD_B = "bbbbbbbb-6666-4666-8666-666666666666";

/**
 * A minimal agent config.
 *
 * @returns {object} The config.
 */
function makeConfig() {
  return {
    model_name: "steerable-model",
    inference: { format: "steerable", base_url: "https://openrouter.ai/api/v1" },
  };
}

/**
 * Build a session detail.
 *
 * @param {string} id The session id.
 * @param {string} name The session name.
 * @param {string} touched The last-touched timestamp.
 * @param {Array<object>} threads The session's threads.
 * @returns {object} The session detail.
 */
function makeSession(id, name, touched, threads) {
  return {
    id,
    agent_id: AGENT_A,
    name,
    created_at: "2026-01-01T00:00:00Z",
    last_touched_at: touched,
    config: makeConfig(),
    status: "ACTIVE",
    threads,
  };
}

/**
 * The scripted tree: two agents, one with two sessions.
 *
 * @returns {object} The tree data.
 */
function makeTree() {
  const threadA = {
    id: THREAD_A,
    name: "discuss",
    created_at: "2026-01-01T00:00:00Z",
    last_touched_at: "2026-01-01T00:00:00Z",
    is_open: true,
    status: "AWAITING_USER",
    mode: "chat",
    phase: null,
  };
  const threadB = {
    id: THREAD_B,
    name: "execute",
    created_at: "2026-01-01T00:00:00Z",
    last_touched_at: "2026-01-01T00:00:00Z",
    is_open: false,
    status: "AWAITING_USER",
    mode: "chat",
    phase: null,
  };

  return {
    agents: [
      {
        id: AGENT_A,
        name: "coder",
        created_at: "2026-01-01T00:00:00Z",
        last_touched_at: "2026-01-01T00:00:00Z",
        config: makeConfig(),
      },
      {
        id: AGENT_B,
        name: "writer",
        created_at: "2026-01-01T00:00:00Z",
        last_touched_at: "2026-01-01T00:00:00Z",
        config: makeConfig(),
      },
    ],
    sessions: {
      [SESSION_OLD]: makeSession(SESSION_OLD, "old-work", "2026-01-01T00:00:00Z", [threadA]),
      [SESSION_NEW]: makeSession(SESSION_NEW, "new-work", "2026-06-01T00:00:00Z", [threadB]),
    },
    agentSessions: {
      [AGENT_A]: [SESSION_OLD, SESSION_NEW],
      [AGENT_B]: [],
    },
  };
}

/**
 * Install a `fetch` stub serving the tree endpoints.
 *
 * @param {object} tree The scripted tree.
 * @returns {{requests: Array<object>}} The recorded requests.
 */
function installFetchStub(tree) {
  const requests = [];
  globalThis.fetch = async (url) => {
    const href = String(url);
    requests.push({ url: href });

    const json = (payload) =>
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });

    if (href.endsWith("/agents")) {
      return json(tree.agents);
    }

    const agentMatch = href.match(/\/agent\/([^/]+)$/);
    if (agentMatch) {
      const id = decodeURIComponent(agentMatch[1]);
      const agent = tree.agents.find((a) => a.id === id || a.name === id);
      if (!agent) return json({ detail: "not found" });
      return json({
        ...agent,
        sessions: (tree.agentSessions[agent.id] || []).map((sid) => ({
          id: sid,
          name: tree.sessions[sid].name,
          created_at: tree.sessions[sid].created_at,
          last_touched_at: tree.sessions[sid].last_touched_at,
          status: tree.sessions[sid].status,
          thread_count: tree.sessions[sid].threads.length,
        })),
      });
    }

    const sessionMatch = href.match(/\/agent\/([^/]+)\/session\/([^/]+)$/);
    if (sessionMatch) {
      const sid = decodeURIComponent(sessionMatch[2]);
      if (!tree.sessions[sid]) return json({ detail: "not found" });
      return json(tree.sessions[sid]);
    }

    return json({});
  };
  return { requests };
}

/**
 * Render the hook in a probe component and return its latest state.
 *
 * @param {object} options Render options.
 * @returns {Promise<object>} The render handle plus the probe's latest state.
 */
async function renderHook(options = {}) {
  const tree = options.tree ?? makeTree();
  const stub = installFetchStub(tree);
  const state = { current: null };

  function Probe() {
    const value = useAgentsTree();
    state.current = value;
    return null;
  }

  const handle = await renderComponent(React.createElement(Probe));
  return { ...handle, ...stub, state };
}

/** Flush pending promise-driven updates. */
async function settle(ms = 40) {
  const { act } = await import("react");
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms));
  });
}

/** Set the browser URL query string. */
function setSearch(search) {
  window.history.pushState({}, "", `/${search}`);
}

before(async () => {
  cleanupDom = setupClientDom();
  window = globalThis.window;
  React = (await import("react")).default;
  ({ useAgentsTree } = await loadModule("hooks/useAgentsTree.ts"));
});

after(async () => {
  await cleanupModules();
  cleanupDom?.cleanup();
});

beforeEach(() => {
  window.history.pushState({}, "", "/");
});

test("REQ-032: the tree is loaded from the agent, session and thread endpoints", async () => {
  const { requests, unmount } = await renderHook();
  await settle();

  assert.ok(requests.some((request) => request.url.endsWith("/agents")));
  assert.ok(
    requests.some((request) => request.url.includes(`/agent/${AGENT_A}`)),
    "expected the agent detail to be fetched"
  );
  assert.ok(
    requests.some((request) => request.url.includes(`/session/${SESSION_NEW}`)),
    "expected the session details to be fetched"
  );

  await unmount();
});

test("REQ-005: the loaded agents carry their sessions", async () => {
  const { state, unmount } = await renderHook();
  await settle();

  assert.equal(state.current.agents.length, 2);
  assert.equal(state.current.agents[0].sessionsMap[SESSION_OLD].name, "old-work");
  assert.equal(state.current.agents[0].sessionsMap[SESSION_NEW].name, "new-work");

  await unmount();
});

test("REQ-032: the most recently touched session is selected by default", async () => {
  const { state, unmount } = await renderHook();
  await settle();

  assert.equal(state.current.selectedAgentId, AGENT_A);
  assert.equal(state.current.selectedSessionId, SESSION_NEW);

  await unmount();
});

test("REQ-032: the selection is hydrated from the URL by agent slug", async () => {
  setSearch("?agent=writer");

  const { state, unmount } = await renderHook();
  await settle();

  assert.equal(state.current.selectedAgentId, AGENT_B);
  assert.equal(state.current.selectedSessionId, null);

  await unmount();
});

test("REQ-032: the session is hydrated from the URL by session slug", async () => {
  setSearch("?agent=coder&session=old-work");

  const { state, unmount } = await renderHook();
  await settle();

  assert.equal(state.current.selectedAgentId, AGENT_A);
  assert.equal(state.current.selectedSessionId, SESSION_OLD);

  await unmount();
});

test("REQ-032: the thread is hydrated from the URL by thread slug", async () => {
  setSearch("?agent=coder&session=new-work&thread=execute");

  const { state, unmount } = await renderHook();
  await settle();

  assert.equal(state.current.selectedThreadId, THREAD_B);

  await unmount();
});

test("REQ-005: the entities can also be addressed by their canonical UUID", async () => {
  setSearch(`?agent=${AGENT_A}&session=${SESSION_OLD}&thread=${THREAD_A}`);

  const { state, unmount } = await renderHook();
  await settle();

  assert.equal(state.current.selectedAgentId, AGENT_A);
  assert.equal(state.current.selectedSessionId, SESSION_OLD);
  assert.equal(state.current.selectedThreadId, THREAD_A);

  await unmount();
});

test("REQ-032: a browser Back navigation re-resolves the selection", async () => {
  const { state, unmount } = await renderHook();
  await settle();

  assert.equal(state.current.selectedSessionId, SESSION_NEW);

  // Simulate the user navigating back to a deep link.
  setSearch("?agent=coder&session=old-work&thread=discuss");
  window.dispatchEvent(new window.Event("popstate"));
  await settle();

  assert.equal(state.current.selectedSessionId, SESSION_OLD);
  assert.equal(state.current.selectedThreadId, THREAD_A);

  await unmount();
});

test("REQ-032: selecting an agent selects its most recent session", async () => {
  const { state, unmount } = await renderHook();
  await settle();

  state.current.selectAgent(AGENT_A);
  await settle();

  assert.equal(state.current.selectedAgentId, AGENT_A);
  assert.equal(state.current.selectedSessionId, SESSION_NEW);
  assert.equal(state.current.selectedThreadId, null);

  await unmount();
});

test("REQ-032: selecting a session clears the thread selection", async () => {
  const { state, unmount } = await renderHook();
  await settle();

  state.current.selectThread(AGENT_A, SESSION_OLD, THREAD_A);
  await settle();
  assert.equal(state.current.selectedThreadId, THREAD_A);

  state.current.selectSession(AGENT_A, SESSION_OLD);
  await settle();

  assert.equal(state.current.selectedSessionId, SESSION_OLD);
  assert.equal(state.current.selectedThreadId, null);

  await unmount();
});

test("REQ-005: the active thread falls back to the open thread", async () => {
  const { state, unmount } = await renderHook();
  await settle();

  state.current.selectSession(AGENT_A, SESSION_NEW);
  await settle();

  const thread = state.current.activeThread;
  assert.ok(thread);
  assert.equal(thread.is_open, false, "the only thread of the session is the fallback");

  await unmount();
});

test("REQ-005: an empty tree selects nothing", async () => {
  const { state, unmount } = await renderHook({
    tree: { agents: [], sessions: {}, agentSessions: {} },
  });
  await settle();

  assert.equal(state.current.agents.length, 0);
  assert.equal(state.current.selectedAgentId, null);
  assert.equal(state.current.selectedSessionId, null);

  await unmount();
});
