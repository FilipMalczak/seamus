/**
 * Component tests for `ConfigModal` — the dual-mode configuration editor.
 *
 * `ConfigModal` implements REQ-041 / INV-051: the *same* configuration is
 * editable through a guided form and through a raw JSON editor, and the two
 * views must not disagree. Its contracts are:
 *
 *   - the form and the JSON editor are two views of one draft, so a change
 *     made in the form is visible in the JSON editor and vice versa;
 *   - the reasoning-effort selector sits next to the model identifier and
 *     exposes every tier the backend accepts (REQ-047);
 *   - a symbolic `${secret(...)}` API key is *unmasked* so the operator can
 *     verify the path, while a raw secret stays masked (REQ-035 / INV-042);
 *   - the enum guards the backend enforces are enforced in the editor too:
 *     an unknown `todo_implementation`, `skills_implementation`,
 *     `web_search` or `artifacts_implementation` is rejected before saving;
 *   - enabling the naming daemon without a model is rejected;
 *   - invalid JSON blocks the switch back to the form view.
 *
 * The component is driven through a real DOM with `react-dom/client`.
 */

import assert from "node:assert/strict";
import test, { after, before } from "node:test";

import { click, renderComponent, setupClientDom, type } from "./helpers/clientDom.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let cleanupDom;
let React;
let ConfigModal;

/**
 * A representative agent configuration.
 *
 * @param {object} overrides Field overrides.
 * @returns {object} The configuration.
 */
function makeConfig(overrides = {}) {
  return {
    model_name: "openai/gpt-oss-120b",
    mode: "plan",
    todo_implementation: "deepagents",
    skills_implementation: "seamus",
    web_search: "duckduckgo",
    artifacts_implementation: "seamus",
    system_prompt: null,
    inference: {
      format: "openai",
      base_url: "https://openrouter.ai/api/v1",
      api_key: "${secret('/api-key/inference/openrouter')}",
      reasoning_effort: "default",
    },
    daemons: {
      naming: {
        enabled: true,
        model: "openai/gpt-oss-20b",
      },
    },
    ...overrides,
  };
}

/**
 * Render the config modal.
 *
 * @param {object} options Render options.
 * @returns {Promise<object>} The render handle plus recorded handler calls.
 */
async function renderConfig(options = {}) {
  const calls = { saved: [], closed: 0 };
  const handle = await renderComponent(
    React.createElement(ConfigModal, {
      title: options.title ?? "Agent Configuration",
      initialConfig: options.initialConfig ?? makeConfig(),
      isOpen: options.isOpen ?? true,
      onClose: () => {
        calls.closed += 1;
      },
      onSave: async (config) => {
        calls.saved.push(config);
        if (options.saveError) throw new Error(options.saveError);
      },
    })
  );
  return { ...handle, calls };
}

/** The button carrying the given label text. */
function buttonByText(container, text) {
  return Array.from(container.querySelectorAll("button")).find(
    (button) => button.textContent.trim() === text
  );
}

/** The button carrying the given title. */
function buttonByTitle(container, title) {
  return container.querySelector(`button[title="${title}"]`);
}

/** The form field whose label carries the given text. */
function fieldByLabel(container, labelText) {
  return Array.from(container.querySelectorAll(".config-field")).find((field) => {
    const label = field.querySelector(".config-label");
    return label && label.textContent.includes(labelText);
  });
}

/** The save button. */
function saveButton(container) {
  return buttonByText(container, "Save Configuration");
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
  ({ ConfigModal } = await loadModule("components/ConfigModal.tsx"));
});

after(async () => {
  await cleanupModules();
  cleanupDom?.cleanup();
});

test("REQ-041: a closed modal renders nothing", async () => {
  const { container, unmount } = await renderConfig({ isOpen: false });

  assert.equal(container.querySelector(".modal-panel"), null);

  await unmount();
});

test("REQ-041: the modal is titled after its scope", async () => {
  const { container, unmount } = await renderConfig({ title: "Config Template" });

  assert.match(container.querySelector(".modal-title").textContent, /Config Template/);

  await unmount();
});

test("REQ-041: the form and the JSON editor are two views of one draft", async () => {
  const { container, unmount } = await renderConfig();

  // Change the model in the form.
  const modelInput = fieldByLabel(container, "Model Identifier").querySelector(".config-input");
  await type(modelInput, "anthropic/claude-sonnet-4");

  // Switch to the JSON editor and confirm the same value is there.
  await click(buttonByText(container, "Raw JSON"));
  const textarea = container.querySelector(".json-textarea");
  assert.ok(textarea);
  assert.match(textarea.value, /anthropic\/claude-sonnet-4/);

  await unmount();
});

test("REQ-041: a JSON edit is visible in the form", async () => {
  const { container, unmount } = await renderConfig();

  await click(buttonByText(container, "Raw JSON"));
  const textarea = container.querySelector(".json-textarea");
  const edited = JSON.stringify({
    ...makeConfig(),
    model_name: "google/gemini-2.5-pro",
  });
  await type(textarea, edited);

  await click(buttonByText(container, "Form"));
  const modelInput = fieldByLabel(container, "Model Identifier").querySelector(".config-input");
  assert.equal(modelInput.value, "google/gemini-2.5-pro");

  await unmount();
});

test("REQ-047: the reasoning-effort selector sits next to the model identifier", async () => {
  const { container, unmount } = await renderConfig();

  const effortField = fieldByLabel(container, "Reasoning Effort");
  assert.ok(effortField, "expected a Reasoning Effort field");

  const row = effortField.parentElement;
  assert.ok(
    row.textContent.includes("Model Identifier"),
    "the reasoning effort must be adjacent to the model identifier"
  );

  await unmount();
});

test("REQ-047: every reasoning-effort tier is offered", async () => {
  const { container, unmount } = await renderConfig();

  const select = fieldByLabel(container, "Reasoning Effort").querySelector("select");
  const values = Array.from(select.options).map((option) => option.value);

  assert.deepEqual(values, [
    "default",
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
  ]);

  await unmount();
});

test("REQ-047: the selected reasoning effort is the one from the config", async () => {
  const { container, unmount } = await renderConfig({
    initialConfig: makeConfig({
      inference: {
        format: "openai",
        base_url: "https://openrouter.ai/api/v1",
        api_key: null,
        reasoning_effort: "high",
      },
    }),
  });

  const select = fieldByLabel(container, "Reasoning Effort").querySelector("select");
  assert.equal(select.value, "high");

  await unmount();
});

test("REQ-047: changing the reasoning effort updates the saved configuration", async () => {
  const { container, unmount, calls } = await renderConfig();

  const select = fieldByLabel(container, "Reasoning Effort").querySelector("select");
  await type(select, "medium");

  await click(saveButton(container));
  await settle();

  assert.equal(calls.saved.length, 1);
  assert.equal(calls.saved[0].inference.reasoning_effort, "medium");

  await unmount();
});

test("REQ-035: a symbolic secret expression is shown unmasked", async () => {
  const { container, unmount } = await renderConfig();

  const apiKeyField = fieldByLabel(container, "API Key");
  const input = apiKeyField.querySelector(".config-input");
  assert.equal(input.type, "text", "a symbolic secret must be readable");
  assert.match(input.value, /\$\{secret\(/);

  await unmount();
});

test("REQ-035: a raw secret stays masked until it is revealed", async () => {
  const { container, unmount } = await renderConfig({
    initialConfig: makeConfig({
      inference: {
        format: "openai",
        base_url: "https://openrouter.ai/api/v1",
        api_key: "sk-raw-secret",
        reasoning_effort: "default",
      },
    }),
  });

  const apiKeyField = fieldByLabel(container, "API Key");
  const input = apiKeyField.querySelector(".config-input");
  assert.equal(input.type, "password");

  await click(buttonByTitle(container, "Show API key"));
  assert.equal(input.type, "text");

  await unmount();
});

test("REQ-035: the API key can be cleared back to null", async () => {
  const { container, unmount, calls } = await renderConfig();

  await click(buttonByText(container, "Clear (set null)"));
  await click(saveButton(container));
  await settle();

  assert.equal(calls.saved.length, 1);
  assert.equal(calls.saved[0].inference.api_key, null);

  await unmount();
});

test("REQ-050: an invalid artifacts implementation is rejected before saving", async () => {
  const { container, unmount, calls } = await renderConfig();

  await click(buttonByText(container, "Raw JSON"));
  const textarea = container.querySelector(".json-textarea");
  await type(textarea, JSON.stringify({ ...makeConfig(), artifacts_implementation: "bogus" }));

  await click(saveButton(container));
  await settle();

  assert.equal(calls.saved.length, 0, "an invalid configuration must not be saved");
  assert.match(container.querySelector(".alert-error").textContent, /artifacts_implementation/);

  await unmount();
});

test("REQ-029: an invalid todo implementation is rejected before saving", async () => {
  const { container, unmount, calls } = await renderConfig();

  await click(buttonByText(container, "Raw JSON"));
  const textarea = container.querySelector(".json-textarea");
  await type(textarea, JSON.stringify({ ...makeConfig(), todo_implementation: "bogus" }));

  await click(saveButton(container));
  await settle();

  assert.equal(calls.saved.length, 0);
  assert.match(container.querySelector(".alert-error").textContent, /todo_implementation/);

  await unmount();
});

test("REQ-044: an invalid web search implementation is rejected before saving", async () => {
  const { container, unmount, calls } = await renderConfig();

  await click(buttonByText(container, "Raw JSON"));
  const textarea = container.querySelector(".json-textarea");
  await type(textarea, JSON.stringify({ ...makeConfig(), web_search: "bogus" }));

  await click(saveButton(container));
  await settle();

  assert.equal(calls.saved.length, 0);
  assert.match(container.querySelector(".alert-error").textContent, /web_search/);

  await unmount();
});

test("REQ-039: enabling the naming daemon without a model is rejected", async () => {
  const { container, unmount, calls } = await renderConfig();

  await click(buttonByText(container, "Raw JSON"));
  const textarea = container.querySelector(".json-textarea");
  await type(
    textarea,
    JSON.stringify({
      ...makeConfig(),
      daemons: { naming: { enabled: true, model: "" } },
    })
  );

  await click(saveButton(container));
  await settle();

  assert.equal(calls.saved.length, 0);
  assert.match(container.querySelector(".alert-error").textContent, /Naming daemon model/);

  await unmount();
});

test("REQ-041: invalid JSON blocks the switch back to the form view", async () => {
  const { container, unmount } = await renderConfig();

  await click(buttonByText(container, "Raw JSON"));
  const textarea = container.querySelector(".json-textarea");
  await type(textarea, "{ not json");

  await click(buttonByText(container, "Form"));

  assert.match(container.querySelector(".alert-error").textContent, /Fix JSON syntax errors/);
  assert.ok(container.querySelector(".json-textarea"), "the JSON editor stays open");

  await unmount();
});

test("REQ-041: invalid JSON is rejected before saving", async () => {
  const { container, unmount, calls } = await renderConfig();

  await click(buttonByText(container, "Raw JSON"));
  const textarea = container.querySelector(".json-textarea");
  await type(textarea, "{ not json");

  await click(saveButton(container));
  await settle();

  assert.equal(calls.saved.length, 0);
  assert.match(container.querySelector(".alert-error").textContent, /Invalid JSON syntax/);

  await unmount();
});

test("REQ-041: a successful save reports success", async () => {
  const { container, unmount, calls } = await renderConfig();

  await click(saveButton(container));
  await settle();

  assert.equal(calls.saved.length, 1);
  assert.match(container.querySelector(".alert-success").textContent, /saved successfully/);

  await unmount();
});

test("REQ-041: a failing save surfaces the error and does not close the modal", async () => {
  const { container, unmount, calls } = await renderConfig({ saveError: "Gitea rejected the write" });

  await click(saveButton(container));
  await settle();

  assert.match(container.querySelector(".alert-error").textContent, /Gitea rejected the write/);
  assert.equal(calls.closed, 0, "a failed save must not close the modal");

  await unmount();
});

test("REQ-041: cancelling closes the modal without saving", async () => {
  const { container, unmount, calls } = await renderConfig();

  await click(buttonByText(container, "Cancel"));

  assert.equal(calls.saved.length, 0);
  assert.equal(calls.closed, 1);

  await unmount();
});

test("REQ-041: the JSON editor can reformat the document", async () => {
  const { container, unmount } = await renderConfig();

  await click(buttonByText(container, "Raw JSON"));
  const textarea = container.querySelector(".json-textarea");
  await type(textarea, '{"model_name":"x"}');

  await click(buttonByTitle(container, "Format and indent JSON"));

  assert.match(textarea.value, /\n\s{2}"model_name"/);

  await unmount();
});
