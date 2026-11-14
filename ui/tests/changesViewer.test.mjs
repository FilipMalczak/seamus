/**
 * Component tests for `ChangesViewer` — the Sync PR diff tab.
 *
 * `ChangesViewer` owns the user-facing half of REQ-021 / INV-024:
 *
 *   - the active Sync PR is identified by number and linked to Gitea when a
 *     PR URL is known, and the absence of a PR is stated explicitly;
 *   - deliverable files are listed with their git status badge and their
 *     addition/deletion stats;
 *   - the file filter narrows the list to matching paths only;
 *   - the Accept action is placed in the Changes header and is *disabled*
 *     when the thread is closed or the agent is busy, so a merge can never be
 *     triggered from an unsafe state;
 *   - the sidebar can be collapsed and the diff style switched between
 *     unified and split.
 *
 * The component is driven against a stubbed `fetch`, so the real
 * `getSessionDiff` / `listArtifacts` client calls and the real
 * `parsePatchFiles` diff parser run against a genuine unified diff.
 */

import assert from "node:assert/strict";
import test, { after, before, beforeEach } from "node:test";

import { click, renderComponent, setupClientDom, type } from "./helpers/clientDom.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let cleanupDom;
let React;
let ChangesViewer;

const AGENT_ID = "11111111-1111-4111-8111-111111111111";
const SESSION_ID = "22222222-2222-4222-8222-222222222222";
const THREAD_ID = "33333333-3333-4333-8333-333333333333";

/**
 * A genuine unified diff touching two files, one added and one modified.
 */
const DIFF = `diff --git a/src/new_module.py b/src/new_module.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/new_module.py
@@ -0,0 +1,2 @@
+def alpha():
+    return 1
diff --git a/src/existing.py b/src/existing.py
index 1111111..2222222 100644
--- a/src/existing.py
+++ b/src/existing.py
@@ -1,2 +1,2 @@
-old()
+new()
 context()
`;

/**
 * Install a `fetch` stub serving the diff and artifact endpoints.
 *
 * @param {object} options Stub options.
 * @returns {{calls: Array<object>}} The recorded calls.
 */
function installFetchStub(options = {}) {
  const calls = [];
  globalThis.fetch = async (url) => {
    const href = String(url);
    calls.push({ url: href });

    if (href.includes("/diff")) {
      return new Response(
        JSON.stringify({
          agent_id: AGENT_ID,
          session_id: SESSION_ID,
          pr_number:
            "prNumber" in options ? options.prNumber : 7,
          pr_url:
            "prUrl" in options
              ? options.prUrl
              : "http://gitea.local/seamus/agent-x/pulls/7",
          diff: "diff" in options ? options.diff : DIFF,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    if (href.includes("/artifact")) {
      return new Response(JSON.stringify(options.artifacts ?? []), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response("{}", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  return { calls };
}

/**
 * Render the changes viewer.
 *
 * @param {object} options Render options.
 * @returns {Promise<object>} The render handle.
 */
async function renderChanges(options = {}) {
  const stub = installFetchStub(options);
  const handle = await renderComponent(
    React.createElement(ChangesViewer, {
      agentId: "agentId" in options ? options.agentId : AGENT_ID,
      agentName: "agentName" in options ? options.agentName : "agent",
      sessionId: "sessionId" in options ? options.sessionId : SESSION_ID,
      sessionName: "sessionName" in options ? options.sessionName : "session",
      thread: options.thread ?? {
        id: THREAD_ID,
        name: "thread",
        created_at: "2026-01-01T00:00:00Z",
        last_touched_at: "2026-01-01T00:00:00Z",
        is_open: options.isOpen ?? true,
        status: options.status ?? "AWAITING_USER",
        mode: "chat",
        phase: null,
      },
      agentStatus: options.agentStatus,
      onAcceptThread: options.onAcceptThread,
    })
  );
  return { ...handle, ...stub };
}

/** Flush the pending promise-driven render updates. */
async function settle() {
  const { act } = await import("react");
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
}

before(async () => {
  cleanupDom = setupClientDom();
  React = (await import("react")).default;
  ({ ChangesViewer } = await loadModule("components/ChangesViewer.tsx"));
});

after(async () => {
  await cleanupModules();
  cleanupDom?.cleanup();
});

beforeEach(() => {
  globalThis.alert = () => {};
});

test("REQ-021: the active Sync PR is identified by number and linked to Gitea", async () => {
  const { container, unmount } = await renderChanges();

  const link = container.querySelector("a.changes-pr-badge");
  assert.ok(link, "expected a linked Sync PR badge");
  assert.match(link.textContent, /Sync PR #7/);
  assert.equal(link.getAttribute("href"), "http://gitea.local/seamus/agent-x/pulls/7");
  assert.equal(link.getAttribute("target"), "_blank");

  await unmount();
});

test("REQ-021: the absence of an active Sync PR is stated explicitly", async () => {
  const { container, unmount } = await renderChanges({ prNumber: null });

  const badge = container.querySelector(".changes-pr-none");
  assert.ok(badge);
  assert.match(badge.textContent, /No active Sync PR/);

  await unmount();
});

test("REQ-021: a Sync PR without a URL is shown as a plain badge", async () => {
  const { container, unmount } = await renderChanges({ prUrl: null });

  assert.equal(container.querySelector("a.changes-pr-badge"), null);
  const badge = container.querySelector("span.changes-pr-badge");
  assert.ok(badge);
  assert.match(badge.textContent, /Sync PR #7/);

  await unmount();
});

test("REQ-021: the agent and session are shown in the subtitle", async () => {
  const { container, unmount } = await renderChanges();

  const subtitle = container.querySelector(".changes-subtitle");
  assert.ok(subtitle);
  assert.match(subtitle.textContent, /agent/);
  assert.match(subtitle.textContent, /session/);

  await unmount();
});

test("REQ-021: the changed files are listed with their stats", async () => {
  const { container, unmount } = await renderChanges();
  await settle();

  const names = Array.from(container.querySelectorAll(".changes-tree-file-name")).map(
    (el) => el.textContent
  );
  assert.ok(names.includes("new_module.py"));
  assert.ok(names.includes("existing.py"));

  const stats = Array.from(container.querySelectorAll(".stat-add")).map(
    (el) => el.textContent
  );
  assert.ok(stats.includes("+2"), "the added file contributes two additions");

  await unmount();
});

test("REQ-021: the file filter narrows the list to matching paths", async () => {
  const { container, unmount } = await renderChanges();
  await settle();

  const filter = container.querySelector(".changes-search-input");
  assert.ok(filter, "expected a file filter input");

  await type(filter, "existing");
  await settle();

  const names = Array.from(container.querySelectorAll(".changes-tree-file-name")).map(
    (el) => el.textContent
  );
  assert.ok(names.includes("existing.py"));
  assert.ok(!names.includes("new_module.py"), "the non-matching file is filtered out");

  await unmount();
});

test("REQ-021: the diff style can be switched between unified and split", async () => {
  const { container, unmount } = await renderChanges();
  await settle();

  const split = container.querySelector('button[title="Split (side-by-side) diff"]');
  const unified = container.querySelector('button[title="Unified diff"]');
  assert.ok(split);
  assert.ok(unified);

  assert.match(unified.className, /active/);
  await click(split);

  assert.match(split.className, /active/);
  assert.doesNotMatch(unified.className, /active/);

  await unmount();
});

test("REQ-021: the changed-files sidebar can be collapsed and restored", async () => {
  const { container, unmount } = await renderChanges();
  await settle();

  const toggle = container.querySelector('button[aria-label="Toggle changed files sidebar"]');
  assert.ok(toggle);

  assert.ok(container.querySelector(".changes-files-sidebar"));
  await click(toggle);
  assert.equal(container.querySelector(".changes-files-sidebar"), null);

  await click(toggle);
  assert.ok(container.querySelector(".changes-files-sidebar"));

  await unmount();
});

test("INV-024: the Accept action lives in the Changes header", async () => {
  const { container, unmount } = await renderChanges({ onAcceptThread: async () => {} });

  const accept = container.querySelector(".btn-accept");
  assert.ok(accept);
  assert.ok(
    container.querySelector(".changes-header").contains(accept),
    "the Accept button must be placed in the Changes header"
  );

  await unmount();
});

test("INV-024: the Accept action is enabled for an open, idle thread", async () => {
  const { container, unmount } = await renderChanges({ onAcceptThread: async () => {} });

  const accept = container.querySelector(".btn-accept");
  assert.equal(accept.disabled, false);
  assert.match(accept.className, /btn-accept-active/);

  await unmount();
});

test("INV-024: the Accept action is disabled for a closed thread", async () => {
  const { container, unmount } = await renderChanges({
    isOpen: false,
    onAcceptThread: async () => {},
  });

  const accept = container.querySelector(".btn-accept");
  assert.equal(accept.disabled, true);
  assert.match(accept.className, /btn-accept-disabled/);
  assert.equal(accept.getAttribute("title"), "Thread is closed");

  await unmount();
});

test("INV-024: the Accept action is disabled while the agent is busy", async () => {
  const { container, unmount } = await renderChanges({
    status: "AWAITING_LLM",
    onAcceptThread: async () => {},
  });

  const accept = container.querySelector(".btn-accept");
  assert.equal(accept.disabled, true);
  assert.equal(accept.getAttribute("title"), "Agent is currently busy");

  await unmount();
});

test("INV-024: clicking Accept invokes the accept handler", async () => {
  const calls = [];
  const { container, unmount } = await renderChanges({
    onAcceptThread: async () => {
      calls.push("accept");
    },
  });

  await click(container.querySelector(".btn-accept"));
  await settle();

  assert.deepEqual(calls, ["accept"]);

  await unmount();
});

test("REQ-021: the diff is fetched for the active session", async () => {
  const { calls, unmount } = await renderChanges();
  await settle();

  assert.ok(
    calls.some((call) => call.url.includes(`/agent/${AGENT_ID}/session/${SESSION_ID}/diff`)),
    "expected a diff request for the active session"
  );

  await unmount();
});

test("REQ-021: no session selected renders the empty state instead of fetching", async () => {
  const { container, calls, unmount } = await renderChanges({
    agentId: null,
    sessionId: null,
  });
  await settle();

  assert.match(container.querySelector(".changes-empty-state").textContent, /Select a session/);
  assert.equal(calls.length, 0, "no session means no requests");

  await unmount();
});

test("REQ-021: an empty diff renders the no-changes state", async () => {
  const { container, unmount } = await renderChanges({ diff: "" });
  await settle();

  assert.ok(container.querySelector(".changes-empty-state"));

  await unmount();
});
