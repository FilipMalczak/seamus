/**
 * Component tests for `Header` — the application header bar.
 *
 * The header carries three user-visible contracts that no other test covers:
 *
 *   - REQ-041 / INV-051 — the header renders the *config template*'s model
 *                         name and base URL, not the selected agent's, so a
 *                         stale agent config cannot silently mislabel the
 *                         running model;
 *   - REQ-008 — the two header actions (System Settings and Config Template)
 *               are the only entry points to the configuration editors;
 *   - REQ-013 — the base URL is exposed as a tooltip with its full value,
 *               while the visible label is shortened.
 *
 * The component is rendered from the real production source through the
 * esbuild-based `loadModule` helper; no network or inference is involved.
 */

import assert from "node:assert/strict";
import test, { after, before } from "node:test";

import { click, renderComponent, setupClientDom } from "./helpers/clientDom.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let cleanupDom;
let React;
let Header;

/**
 * A minimal agent config that satisfies the header's field access.
 *
 * @param {object} overrides Field overrides.
 * @returns {object} The config.
 */
function makeConfig(overrides = {}) {
  return {
    model_name: "steerable-model",
    inference: {
      format: "steerable",
      base_url: "https://openrouter.ai/api/v1",
      ...(overrides.inference || {}),
    },
    ...overrides,
  };
}

/**
 * Render the header with the given config template.
 *
 * @param {object|null} configTemplate The template config.
 * @returns {Promise<object>} The render handle plus recorded handler calls.
 */
async function renderHeader(configTemplate) {
  const calls = [];
  const handle = await renderComponent(
    React.createElement(Header, {
      configTemplate,
      onOpenConfigTemplate: () => calls.push("config-template"),
      onOpenSystemSettings: () => calls.push("system-settings"),
    })
  );
  return { ...handle, calls };
}

/** The header element. */
function header(container) {
  return container.querySelector(".app-header");
}

/** The button carrying the given title. */
function buttonByTitle(container, title) {
  return container.querySelector(`button[title="${title}"]`);
}

before(async () => {
  cleanupDom = setupClientDom();
  React = (await import("react")).default;
  ({ Header } = await loadModule("components/Header.tsx"));
});

after(async () => {
  await cleanupModules();
  cleanupDom?.cleanup();
});

test("REQ-041: the header shows the config template's model name and base URL", async () => {
  const { container, unmount } = await renderHeader(makeConfig());

  const meta = container.querySelector(".brand-meta");
  assert.ok(meta);
  assert.match(meta.textContent, /steerable-model/);
  assert.match(meta.textContent, /openrouter\.ai\/api\/v1/);

  await unmount();
});

test("REQ-041: the header falls back to defaults without a config template", async () => {
  const { container, unmount } = await renderHeader(null);

  const meta = container.querySelector(".brand-meta");
  assert.ok(meta);
  assert.match(meta.textContent, /openai\/gpt-oss-120b/);
  assert.match(meta.textContent, /OpenRouter/);

  await unmount();
});

test("REQ-013: the base URL is exposed in full through the tooltip", async () => {
  const { container, unmount } = await renderHeader(
    makeConfig({ inference: { base_url: "https://openrouter.ai/api/v1" } })
  );

  const urlSpan = container.querySelector('.brand-meta span[title]');
  assert.ok(urlSpan);
  assert.equal(urlSpan.getAttribute("title"), "https://openrouter.ai/api/v1");
  assert.equal(urlSpan.textContent, "openrouter.ai/api/v1");

  await unmount();
});

test("REQ-008: the header renders both configuration entry points", async () => {
  const { container, unmount } = await renderHeader(makeConfig());

  assert.ok(buttonByTitle(container, "Edit System Settings"));
  assert.ok(buttonByTitle(container, "Edit singleton Config Template"));

  await unmount();
});

test("REQ-008: the settings action calls the system-settings handler", async () => {
  const { container, unmount, calls } = await renderHeader(makeConfig());

  await click(buttonByTitle(container, "Edit System Settings"));

  assert.deepEqual(calls, ["system-settings"]);

  await unmount();
});

test("REQ-008: the config-template action calls the config-template handler", async () => {
  const { container, unmount, calls } = await renderHeader(makeConfig());

  await click(buttonByTitle(container, "Edit singleton Config Template"));

  assert.deepEqual(calls, ["config-template"]);

  await unmount();
});

test("REQ-013: the header always advertises the AG-UI transport", async () => {
  const { container, unmount } = await renderHeader(makeConfig());

  assert.match(header(container).textContent, /AG-UI SSE/);

  await unmount();
});
