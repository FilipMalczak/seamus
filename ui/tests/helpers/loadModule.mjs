/**
 * Loads TypeScript/TSX source modules from `ui/src` for Node-based tests.
 *
 * The UI test suite runs on plain Node (`node --test`) without a bundler in
 * the test loop. To avoid duplicating production logic inside the test
 * files — which silently drifts from the implementation — the modules are
 * bundled on demand with esbuild (already a transitive dependency of Vite)
 * and imported from the generated ESM output.
 */

import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import * as esbuild from "esbuild";

const UI_ROOT = resolve(import.meta.dirname, "..", "..");
const SRC_ROOT = join(UI_ROOT, "src");

// Bundles are written inside the UI tree so that Node resolves the
// `external` packages (react, react-dom) from `ui/node_modules`.
const BUNDLE_ROOT = join(UI_ROOT, "node_modules", ".cache", "seamus-ui-test");

const cache = new Map();
const tempDirs = new Set();

/**
 * Bundle a module under `ui/src` and import it.
 *
 * @param {string} relativePath Path relative to `ui/src`, e.g. "utils/sequence.ts".
 * @returns {Promise<Record<string, unknown>>} The imported module namespace.
 */
export async function loadModule(relativePath) {
  if (cache.has(relativePath)) {
    return cache.get(relativePath);
  }

  const entryPoint = join(SRC_ROOT, relativePath);
  const result = await esbuild.build({
    entryPoints: [entryPoint],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    jsx: "automatic",
    loader: { ".ts": "ts", ".tsx": "tsx" },
    external: ["react", "react-dom", "react-dom/server", "react/jsx-runtime"],
    write: false,
    logLevel: "silent",
  });

  await mkdir(BUNDLE_ROOT, { recursive: true });
  const dir = await mkdtemp(join(BUNDLE_ROOT, "bundle-"));
  tempDirs.add(dir);
  const outFile = join(dir, "bundle.mjs");
  await writeFile(outFile, result.outputFiles[0].text, "utf8");

  const mod = await import(pathToFileURL(outFile).href);
  cache.set(relativePath, mod);
  return mod;
}

/** Remove all temporary bundle directories created by {@link loadModule}. */
export async function cleanupModules() {
  for (const dir of tempDirs) {
    await rm(dir, { recursive: true, force: true });
  }
  tempDirs.clear();
  cache.clear();
}
