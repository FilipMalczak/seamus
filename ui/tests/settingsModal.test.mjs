/**
 * Component tests for `SettingsModal` — system settings and vault management.
 *
 * `SettingsModal` implements three separate user-facing surfaces:
 *
 *   - the *skill directories* tab, which warns that system-level skills
 *     bypass workspace isolation (REQ-043 / INV-035);
 *   - the *secrets* tab, which is the in-browser OpenBao management surface
 *     required by REQ-035: the login token is hidden until it is explicitly
 *     revealed, a stored secret is listed by path and version, and each key
 *     exposes a copyable symbolic `${secret(...)}` expression;
 *   - the *raw JSON* tab, which edits the same `skill_directories` list.
 *
 * The secrets that the backend returns are *never* echoed: the modal only
 * receives paths, keys and versions (INV-042).
 *
 * The component is driven against a stubbed `fetch`, so the real API client
 * calls run against scripted vault responses.
 */

import assert from "node:assert/strict";
import test, { after, before, beforeEach } from "node:test";

import { click, renderComponent, setupClientDom, type } from "./helpers/clientDom.mjs";
import { cleanupModules, loadModule } from "./helpers/loadModule.mjs";

let cleanupDom;
let React;
let SettingsModal;

/**
 * Install a `fetch` stub serving the vault endpoints.
 *
 * @param {object} options Stub options.
 * @returns {{requests: Array<object>}} The recorded requests.
 */
function installFetchStub(options = {}) {
  const requests = [];
  globalThis.fetch = async (url, init) => {
    const href = String(url);
    requests.push({ url: href, method: init?.method ?? "GET" });

    if (href.includes("/vault/token")) {
      return new Response(JSON.stringify({ token: options.token ?? "root-token-value" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (href.includes("/vault/secrets") && (init?.method ?? "GET") === "POST") {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (href.includes("/vault/secrets")) {
      return new Response(
        JSON.stringify({
          secrets: options.secrets ?? [
            { path: "api-key/inference/openrouter", keys: ["value"], version: 3 },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response("{}", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  return { requests };
}

/**
 * Render the settings modal.
 *
 * @param {object} options Render options.
 * @returns {Promise<object>} The render handle plus recorded handler calls.
 */
async function renderSettings(options = {}) {
  const stub = installFetchStub(options);
  const calls = { saved: [], closed: 0 };
  const handle = await renderComponent(
    React.createElement(SettingsModal, {
      isOpen: options.isOpen ?? true,
      initialSettings: options.initialSettings ?? {
        skill_directories: ["/opt/skills"],
      },
      onClose: () => {
        calls.closed += 1;
      },
      onSave: async (settings) => {
        calls.saved.push(settings);
      },
    })
  );
  return { ...handle, ...stub, calls };
}

/** The button carrying the given label text. */
function buttonByText(container, text) {
  return Array.from(container.querySelectorAll("button")).find(
    (button) => button.textContent.trim() === text
  );
}

/** The input carrying the given placeholder. */
function inputByPlaceholder(container, placeholder) {
  return container.querySelector(`input[placeholder="${placeholder}"]`);
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
  ({ SettingsModal } = await loadModule("components/SettingsModal.tsx"));
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

test("REQ-041: a closed modal renders nothing", async () => {
  const { container, unmount } = await renderSettings({ isOpen: false });

  assert.equal(container.querySelector(".modal-panel"), null);

  await unmount();
});

test("REQ-043: the skill-directories tab warns about system-level skills", async () => {
  const { container, unmount } = await renderSettings();

  assert.match(container.textContent, /DISRECOMMENDED/);
  assert.match(container.textContent, /bypass workspace isolation/);

  await unmount();
});

test("REQ-043: the configured skill directories are listed", async () => {
  const { container, unmount } = await renderSettings();

  assert.match(container.textContent, /\/opt\/skills/);

  await unmount();
});

test("REQ-043: a skill directory can be added", async () => {
  const { container, unmount, calls } = await renderSettings();

  await type(inputByPlaceholder(container, "Host path (e.g. ~/.seamus/skills or ~/.skills)"), "/srv/skills");
  await click(buttonByText(container, "Add"));

  await click(buttonByText(container, "Save Settings"));
  await settle();

  assert.equal(calls.saved.length, 1);
  assert.deepEqual(calls.saved[0].skill_directories, ["/opt/skills", "/srv/skills"]);

  await unmount();
});

test("REQ-043: a duplicate skill directory is rejected", async () => {
  const { container, unmount, calls } = await renderSettings();

  await type(inputByPlaceholder(container, "Host path (e.g. ~/.seamus/skills or ~/.skills)"), "/opt/skills");
  await click(buttonByText(container, "Add"));

  assert.match(container.querySelector(".alert-error").textContent, /already added/);

  await click(buttonByText(container, "Save Settings"));
  await settle();

  assert.deepEqual(calls.saved[0].skill_directories, ["/opt/skills"]);

  await unmount();
});

test("REQ-043: a skill directory can be removed", async () => {
  const { container, unmount, calls } = await renderSettings();

  await click(container.querySelector('button[title="Remove directory"]'));
  await click(buttonByText(container, "Save Settings"));
  await settle();

  assert.deepEqual(calls.saved[0].skill_directories, []);

  await unmount();
});

test("REQ-041: the raw JSON tab edits the same skill directory list", async () => {
  const { container, unmount, calls } = await renderSettings();

  await click(buttonByText(container, "Raw JSON"));
  const textarea = container.querySelector(".json-textarea");
  assert.match(textarea.value, /skill_directories/);

  await type(textarea, JSON.stringify({ skill_directories: ["/json/skills"] }));
  await click(buttonByText(container, "Save Settings"));
  await settle();

  assert.deepEqual(calls.saved[0].skill_directories, ["/json/skills"]);

  await unmount();
});

test("REQ-041: a raw JSON document without a skill_directories array is rejected", async () => {
  const { container, unmount, calls } = await renderSettings();

  await click(buttonByText(container, "Raw JSON"));
  const textarea = container.querySelector(".json-textarea");
  await type(textarea, JSON.stringify({ other: true }));

  await click(buttonByText(container, "Save Settings"));
  await settle();

  assert.equal(calls.saved.length, 0);
  assert.match(container.querySelector(".alert-error").textContent, /skill_directories/);

  await unmount();
});

test("REQ-035: the secrets tab lists the stored secrets with their version", async () => {
  const { container, unmount } = await renderSettings();

  await click(buttonByText(container, "Secrets"));
  await settle();

  assert.match(container.textContent, /\/api-key\/inference\/openrouter/);
  assert.match(container.textContent, /v3/);

  await unmount();
});

test("INV-042: the stored secret value is never rendered", async () => {
  const { container, unmount } = await renderSettings({
    secrets: [
      { path: "api-key/inference/openrouter", keys: ["value"], version: 3 },
    ],
  });

  await click(buttonByText(container, "Secrets"));
  await settle();

  // The path and the key are shown; the value itself never is.
  assert.match(container.textContent, /value/);
  assert.doesNotMatch(container.textContent, /root-token-value/);

  await unmount();
});

test("REQ-035: each secret key exposes a copyable symbolic expression", async () => {
  const written = [];
  globalThis.navigator.clipboard = {
    writeText: async (value) => {
      written.push(value);
    },
  };

  const { container, unmount } = await renderSettings();

  await click(buttonByText(container, "Secrets"));
  await settle();

  const exprButton = container.querySelector(
    'button[title="Click to copy ${secret(\'/api-key/inference/openrouter\')}"]'
  );
  assert.ok(exprButton, "expected a copyable expression button");

  await click(exprButton);
  // The button resets its "copied" state on a 2s timer; wait for it so the
  // timer does not fire after the DOM has been torn down.
  await settle(2100);

  assert.deepEqual(written, ["${secret('/api-key/inference/openrouter')}"]);

  await unmount();
});

test("REQ-035: the OpenBao login token is hidden until it is revealed", async () => {
  const { container, unmount, requests } = await renderSettings();

  await click(buttonByText(container, "Secrets"));
  await settle();

  assert.doesNotMatch(container.textContent, /root-token-value/);

  await click(buttonByText(container, "Reveal Token"));
  await settle();

  assert.match(container.textContent, /root-token-value/);
  assert.ok(
    requests.some((call) => call.url.includes("/vault/token")),
    "the token must be fetched from the backend, never hard-coded"
  );

  await unmount();
});

test("REQ-035: the revealed token can be hidden again", async () => {
  const { container, unmount } = await renderSettings();

  await click(buttonByText(container, "Secrets"));
  await settle();

  await click(buttonByText(container, "Reveal Token"));
  await settle();
  await click(buttonByText(container, "Hide"));
  await settle();

  assert.doesNotMatch(container.textContent, /root-token-value/);

  await unmount();
});

test("REQ-035: a secret can be saved with a path and a field", async () => {
  const { container, unmount, requests } = await renderSettings();

  await click(buttonByText(container, "Secrets"));
  await settle();

  await type(
    inputByPlaceholder(container, "Secret path (e.g. /api-key/inference/openrouter)"),
    "/api-key/custom"
  );
  await type(inputByPlaceholder(container, "Secret value"), "s3cret");

  await click(buttonByText(container, "Save Secret"));
  await settle();

  const post = requests.find(
    (call) => call.method === "POST" && call.url.includes("/vault/secrets")
  );
  assert.ok(post, "expected a secret write request");

  await unmount();
});

test("REQ-035: a secret with an empty path is rejected", async () => {
  const { container, unmount, requests } = await renderSettings();

  await click(buttonByText(container, "Secrets"));
  await settle();

  await click(buttonByText(container, "Save Secret"));
  await settle();

  assert.ok(
    !requests.some((call) => call.method === "POST"),
    "an empty secret path must not be written"
  );
  assert.match(container.querySelector(".alert-error").textContent, /path cannot be empty/);

  await unmount();
});

test("REQ-035: a secret field with an empty key is rejected", async () => {
  const { container, unmount, requests } = await renderSettings();

  await click(buttonByText(container, "Secrets"));
  await settle();

  await type(
    inputByPlaceholder(container, "Secret path (e.g. /api-key/inference/openrouter)"),
    "/api-key/custom"
  );
  await type(inputByPlaceholder(container, "Field (default: value)"), "   ");

  await click(buttonByText(container, "Save Secret"));
  await settle();

  assert.ok(!requests.some((call) => call.method === "POST"));
  assert.match(container.querySelector(".alert-error").textContent, /key cannot be empty/);

  await unmount();
});

test("REQ-035: a secret value entered as a symbolic expression stays readable", async () => {
  const { container, unmount } = await renderSettings();

  await click(buttonByText(container, "Secrets"));
  await settle();

  const valueInput = inputByPlaceholder(container, "Secret value");
  assert.equal(valueInput.type, "password", "a raw secret value is masked");

  await type(valueInput, "${secret('/api-key/inference/openrouter')}");
  assert.equal(valueInput.type, "text", "a symbolic expression is readable");

  await unmount();
});

test("REQ-041: a successful save reports success", async () => {
  const { container, unmount, calls } = await renderSettings();

  await click(buttonByText(container, "Save Settings"));
  await settle();

  assert.equal(calls.saved.length, 1);
  assert.match(container.querySelector(".alert-success").textContent, /saved successfully/);

  await unmount();
});

test("REQ-041: cancelling closes the modal without saving", async () => {
  const { container, unmount, calls } = await renderSettings();

  await click(buttonByText(container, "Cancel"));

  assert.equal(calls.saved.length, 0);
  assert.equal(calls.closed, 1);

  await unmount();
});
