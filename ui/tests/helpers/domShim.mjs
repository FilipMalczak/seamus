/**
 * DOM shim for Node-based UI component tests.
 *
 * The UI dependency chain (`@a2ui/react` → `lit-html`) references browser
 * globals such as `HTMLElement`, `document`, and `customElements` at
 * module-evaluation time, which fails under plain Node. The
 * `@lit-labs/ssr-dom-shim` package (already present as a transitive
 * dependency) provides a spec-shaped DOM implementation for exactly this
 * purpose, so the tests reuse it instead of hand-rolling a partial DOM.
 *
 * The shim is intentionally not a full browser: the tests assert on
 * server-rendered markup, not on live browser behaviour.
 */

import {
  customElements,
  document,
  HTMLElement,
  window,
} from "@lit-labs/ssr-dom-shim";

const GLOBAL_KEYS = [
  "HTMLElement",
  "Element",
  "Node",
  "Document",
  "EventTarget",
  "customElements",
  "document",
  "window",
  "navigator",
  "location",
  "matchMedia",
  "requestAnimationFrame",
  "cancelAnimationFrame",
];

/**
 * Install the DOM shim onto `globalThis`.
 *
 * @returns {() => void} A function that removes the installed globals.
 */
export function installDomShim() {
  const previous = new Map();
  const define = (name, value) => {
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
    Object.defineProperty(globalThis, name, {
      value,
      configurable: true,
      writable: true,
    });
  };

  define("HTMLElement", HTMLElement);
  define("Element", HTMLElement);
  define("Node", HTMLElement);
  define("customElements", customElements);
  define("document", document);
  define("window", window);
  define("navigator", window.navigator ?? { userAgent: "node" });
  define("location", window.location ?? { href: "http://localhost/" });
  define("matchMedia", () => ({ matches: false, addEventListener: () => {} }));
  define("requestAnimationFrame", (cb) => setTimeout(() => cb(Date.now()), 0));
  define("cancelAnimationFrame", (id) => clearTimeout(id));

  return () => {
    for (const [name, descriptor] of previous) {
      if (descriptor) {
        Object.defineProperty(globalThis, name, descriptor);
      } else {
        delete globalThis[name];
      }
    }
  };
}

export { GLOBAL_KEYS };
