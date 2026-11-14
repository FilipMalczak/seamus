/**
 * Client-side DOM harness for Node-based UI component tests.
 *
 * The static-markup harness (`domShim.mjs` + `react-dom/server`) can only
 * assert on what a component renders on the first pass. Several UI contracts
 * are *interactional* — inline tree editing, the composer busy guard, the
 * auto-focus effect — and cannot be observed without a live DOM and a real
 * event dispatch.
 *
 * This harness installs a `jsdom` window as the global environment and drives
 * the real production components through `react-dom/client`, so the assertions
 * run against the same code the browser runs.
 */

import { JSDOM } from "jsdom";

/**
 * Globals copied from the jsdom window onto `globalThis`.
 *
 * React DOM reads a number of these at module-evaluation time and during
 * event dispatch, so they must exist before `react-dom/client` is imported.
 */
const WINDOW_GLOBALS = [
  "window",
  "document",
  "navigator",
  "location",
  "history",
  "localStorage",
  "sessionStorage",
  "HTMLElement",
  "HTMLInputElement",
  "HTMLTextAreaElement",
  "HTMLButtonElement",
  "Element",
  "Node",
  "NodeFilter",
  "Text",
  "Comment",
  "DocumentFragment",
  "Event",
  "CustomEvent",
  "customElements",
  "MouseEvent",
  "KeyboardEvent",
  "FocusEvent",
  "InputEvent",
  "PointerEvent",
  "SVGElement",
  "DOMParser",
  "XMLSerializer",
  "MutationObserver",
  "IntersectionObserver",
  "getComputedStyle",
  "requestAnimationFrame",
  "cancelAnimationFrame",
  "matchMedia",
  "CSS",
];

/**
 * Install a jsdom environment onto `globalThis`.
 *
 * @returns {{window: object, cleanup: () => void}} The jsdom window and a
 *   function that restores the previous globals.
 */
export function setupClientDom() {
  const dom = new JSDOM("<!doctype html><html><body></body></html>", {
    url: "http://localhost/",
    pretendToBeVisual: true,
  });
  const { window } = dom;

  const previous = new Map();
  const define = (name, value) => {
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
    Object.defineProperty(globalThis, name, {
      value,
      configurable: true,
      writable: true,
    });
  };

  for (const name of WINDOW_GLOBALS) {
    const value = window[name];
    if (value === undefined) continue;
    define(name, typeof value === "function" && !value.prototype ? value.bind(window) : value);
  }

  // jsdom does not implement `scrollIntoView`, which the chat viewport calls
  // when it pins to the bottom. The stub is a no-op: the tests assert on
  // rendered output, not on scroll positions.
  if (typeof window.Element.prototype.scrollIntoView !== "function") {
    window.Element.prototype.scrollIntoView = function scrollIntoView() {};
  }

  // jsdom implements neither `ResizeObserver` nor `IntersectionObserver`.
  // The diff viewer mounts a web component that observes its own size, so
  // the stubs have to exist before the component is rendered.
  if (!globalThis.ResizeObserver) {
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    define("ResizeObserver", ResizeObserverStub);
  }
  if (!globalThis.IntersectionObserver) {
    class IntersectionObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    }
    define("IntersectionObserver", IntersectionObserverStub);
  }

  // The diff library builds a `CSSStyleSheet` in the constructor of its
  // custom element. jsdom ships a partial `CSSStyleSheet` that cannot be
  // constructed, so a minimal stand-in is installed instead.
  if (!globalThis.CSSStyleSheet) {
    class CSSStyleSheetStub {
      constructor() {
        this.cssRules = [];
      }
      replaceSync() {}
      replace() {
        return Promise.resolve(this);
      }
      insertRule(rule) {
        this.cssRules.push(rule);
        return this.cssRules.length - 1;
      }
      deleteRule() {}
    }
    define("CSSStyleSheet", CSSStyleSheetStub);
  }


  // React's `act` requires this flag to be set while rendering.
  define("IS_REACT_ACT_ENVIRONMENT", true);

  const cleanup = () => {
    for (const [name, descriptor] of previous) {
      if (descriptor) {
        Object.defineProperty(globalThis, name, descriptor);
      } else {
        delete globalThis[name];
      }
    }
    window.close();
  };

  return { window, cleanup };
}

/**
 * Render a React element into a detached container attached to the document.
 *
 * @param {React.ReactElement} element The element to render.
 * @returns {Promise<{container: HTMLElement, rerender: Function, unmount: Function}>}
 *   A handle for driving the rendered tree.
 */
export async function renderComponent(element) {
  const React = (await import("react")).default;
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(element);
  });

  let unmounted = false;

  return {
    container,
    root,
    async rerender(next) {
      await act(async () => {
        root.render(next);
      });
    },
    async unmount() {
      // Unmounting twice throws inside React, and the tests use a safety
      // net that unmounts whatever is still mounted. The guard keeps both
      // paths safe.
      if (unmounted) return;
      unmounted = true;
      await act(async () => {
        root.unmount();
      });
      container.remove();
    },
  };
}

/**
 * Run a callback inside React's `act` scope and flush the resulting updates.
 *
 * @param {() => void} fn The callback to run.
 */
export async function flush(fn) {
  const { act } = await import("react");
  await act(async () => {
    fn();
  });
}

/**
 * Dispatch a click on an element and flush the resulting React updates.
 *
 * @param {Element} element The element to click.
 */
export async function click(element) {
  const { act } = await import("react");
  await act(async () => {
    element.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  });
}

/**
 * Set the value of an input-like element and dispatch an `input` event.
 *
 * React tracks the previous value on the DOM node, so the native setter has
 * to be used for the change to be observed.
 *
 * @param {Element} element The input or textarea to type into.
 * @param {string} value The value to set.
 */
export async function type(element, value) {
  const { act } = await import("react");

  if (element.tagName === "SELECT") {
    // A `<select>` reacts to a `change` event, not to `input`.
    await act(async () => {
      element.value = value;
      element.dispatchEvent(new window.Event("change", { bubbles: true }));
    });
    return;
  }

  const prototype =
    element.tagName === "TEXTAREA"
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, "value").set;
  await act(async () => {
    setter.call(element, value);
    element.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
}

/**
 * Dispatch a keydown event on an element and flush React updates.
 *
 * @param {Element} element The element to press a key on.
 * @param {string} key The `KeyboardEvent.key` value.
 */
export async function pressKey(element, key) {
  const { act } = await import("react");
  await act(async () => {
    element.dispatchEvent(
      new window.KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })
    );
  });
}
