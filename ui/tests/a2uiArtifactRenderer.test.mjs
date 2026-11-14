/**
 * Component tests for `A2UIArtifactRenderer` — the artifact card chrome.
 *
 * The *server-side* half of the artifact contract (a button click is
 * dispatched, recorded and resumes the blocked turn) is covered end-to-end
 * by `tests/e2e/test_artifact_routes.py`. This file covers the *client-side*
 * half that the end-to-end suite cannot observe:
 *
 *   - the card states its lifecycle: `Closed`, `Action Required` for a
 *     blocking artifact, or `Interactive`;
 *   - an embedded artifact can be collapsed and restored;
 *   - a closed artifact renders collapsed and its surface is disabled;
 *   - a read-only artifact disables the surface but still renders it;
 *   - the submitting overlay is shown while a submission is in flight.
 *
 * The A2UI surface itself is rendered by `@a2ui/react`, which needs a real
 * custom-element registry; the assertions here therefore target the card
 * chrome that Seamus itself owns.
 */

import assert from "node:assert/strict";
import test, { after, before } from "node:test";

import { click, renderComponent, setupClientDom } from "./helpers/clientDom.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let cleanupDom;
let React;
let A2UIArtifactRenderer;

/**
 * A representative artifact.
 *
 * @param {object} overrides Field overrides.
 * @returns {object} The artifact.
 */
function makeArtifact(overrides = {}) {
  return {
    family: "questionnaires",
    uuid: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    name: "architecture-questions",
    title: null,
    manifest: {
      name: "Architecture Questions",
      exposition: "embedded",
      blocking: true,
      commentable: false,
      buttons: [],
    },
    body: [
      { id: "root", component: "Column", children: ["intro"] },
      { id: "intro", component: "Text", text: "Which storage engine?" },
    ],
    state: { clicksLeft: {} },
    is_closed: false,
    kind: "questionnaires",
    ...overrides,
  };
}

/**
 * Render the artifact card.
 *
 * @param {object} options Render options.
 * @returns {Promise<object>} The render handle.
 */
async function renderArtifact(options = {}) {
  const handle = await renderComponent(
    React.createElement(A2UIArtifactRenderer, {
      artifact: options.artifact ?? makeArtifact(),
      onSubmit: options.onSubmit,
      onClickButton: options.onClickButton,
      isSubmitting: options.isSubmitting ?? false,
      readOnly: options.readOnly ?? false,
    })
  );
  return handle;
}

/** Flush pending promise-driven updates. */
async function settle(ms = 30) {
  const { act } = await import("react");
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms));
  });
}

before(async () => {
  cleanupDom = setupClientDom();
  React = (await import("react")).default;
  ({ A2UIArtifactRenderer } = await loadModule("components/A2UIArtifactRenderer.tsx"));
});

after(async () => {
  await cleanupModules();
  cleanupDom?.cleanup();
});

test("REQ-033: the artifact card shows its title", async () => {
  const { container, unmount } = await renderArtifact();

  const title = container.querySelector(".artifact-header-title");
  assert.ok(title);
  assert.match(title.textContent, /Architecture Questions/);

  await unmount();
});

test("REQ-033: a blocking artifact is badged as Action Required", async () => {
  const { container, unmount } = await renderArtifact();

  const badge = container.querySelector(".artifact-status-badge");
  assert.ok(badge);
  assert.match(badge.textContent, /Action Required/);

  await unmount();
});

test("REQ-033: a non-blocking artifact is badged as Interactive", async () => {
  const { container, unmount } = await renderArtifact({
    artifact: makeArtifact({
      manifest: {
        name: "Architecture Questions",
        exposition: "embedded",
        blocking: false,
        commentable: false,
        buttons: [],
      },
    }),
  });

  const badge = container.querySelector(".artifact-status-badge");
  assert.ok(badge);
  assert.match(badge.textContent, /Interactive/);

  await unmount();
});

test("REQ-033: a closed artifact is badged as Closed", async () => {
  const { container, unmount } = await renderArtifact({
    artifact: makeArtifact({ is_closed: true }),
  });

  const badge = container.querySelector(".artifact-status-badge");
  assert.ok(badge);
  assert.match(badge.textContent, /Closed/);

  await unmount();
});

test("REQ-033: the card is marked as open or closed", async () => {
  const open = await renderArtifact();
  assert.ok(open.container.querySelector(".artifact-open"));
  await open.unmount();

  const closed = await renderArtifact({ artifact: makeArtifact({ is_closed: true }) });
  assert.ok(closed.container.querySelector(".artifact-closed"));
  await closed.unmount();
});

test("REQ-033: an embedded artifact can be collapsed and restored", async () => {
  const { container, unmount } = await renderArtifact();
  await settle();

  const toggle = container.querySelector(".artifact-collapse-toggle-btn");
  assert.ok(toggle);
  assert.match(toggle.textContent, /Hide/);

  await click(toggle);
  assert.match(toggle.textContent, /View/);
  assert.equal(container.querySelector(".artifact-card-content"), null);

  await click(toggle);
  assert.match(toggle.textContent, /Hide/);
  assert.ok(container.querySelector(".artifact-card-content"));

  await unmount();
});

test("REQ-033: a tabbed artifact has no collapse toggle", async () => {
  const { container, unmount } = await renderArtifact({
    artifact: makeArtifact({
      manifest: {
        name: "Architecture Questions",
        exposition: "tabbed",
        blocking: false,
        commentable: false,
        buttons: [],
      },
    }),
  });
  await settle();

  assert.equal(container.querySelector(".artifact-collapse-toggle-btn"), null);

  await unmount();
});

test("REQ-033: a closed artifact renders collapsed, with no surface", async () => {
  const { container, unmount } = await renderArtifact({
    artifact: makeArtifact({ is_closed: true }),
  });
  await settle();

  assert.ok(container.querySelector(".artifact-collapsed"));
  assert.equal(container.querySelector(".artifact-card-content"), null);

  await unmount();
});

test("REQ-033: a read-only artifact renders its surface without interaction", async () => {
  const { container, unmount } = await renderArtifact({ readOnly: true });
  await settle();

  const host = container.querySelector(".a2ui-surface-host");
  assert.ok(host, "expected the A2UI surface to render");
  assert.match(host.className, /pointer-events-none/);

  await unmount();
});

test("REQ-033: an open artifact renders an interactive surface", async () => {
  const { container, unmount } = await renderArtifact();
  await settle();

  const host = container.querySelector(".a2ui-surface-host");
  assert.ok(host, "expected the A2UI surface to render");
  assert.doesNotMatch(host.className, /pointer-events-none/);

  await unmount();
});

test("REQ-033: the submitting overlay is shown while a submission is in flight", async () => {
  const { container, unmount } = await renderArtifact({ isSubmitting: true });
  await settle();

  const overlay = container.querySelector(".artifact-submitting-overlay");
  assert.ok(overlay);
  assert.match(overlay.textContent, /Submitting/);

  await unmount();
});

test("REQ-033: the submitting overlay is absent when nothing is in flight", async () => {
  const { container, unmount } = await renderArtifact();
  await settle();

  assert.equal(container.querySelector(".artifact-submitting-overlay"), null);

  await unmount();
});

test("REQ-033: a plan artifact is titled after its family when unnamed", async () => {
  const { container, unmount } = await renderArtifact({
    artifact: makeArtifact({
      family: "plans",
      manifest: {
        name: "",
        exposition: "tabbed",
        blocking: false,
        commentable: false,
        buttons: [],
      },
    }),
  });
  await settle();

  assert.match(container.querySelector(".artifact-header-title").textContent, /Plan/);

  await unmount();
});
