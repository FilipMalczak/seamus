# 0038. A2UI Root Component Requirement, Auto-Synthesis, and Incomplete Structure Warnings

Date: 2026-11-07

## Status

Accepted

## Context

In [0037-validate-a2ui-surface-render-on-make-artifact.md](./0037-validate-a2ui-surface-render-on-make-artifact.md), Seamus added strict A2UI component schema validation to prevent invalid components (such as Adaptive Cards-style payloads) from being persisted to disk.

However, an agent can author individually valid A2UI components (e.g. a `Text` widget and a `Button` widget) but omit the root container definition (`id: "root"`). In the A2UI v0.9 specification, the renderer (`MessageProcessor` and `NodeResolver`) resolves component trees starting from a root component whose ID defaults to `'root'`. If no component has `id: "root"`, or if multiple disconnected top-level components exist without a common parent container, `NodeResolver.rootNode` evaluates to `undefined`, and `<A2uiSurface>` renders `null` (an empty panel).

We need to:
1. Ensure artifacts with missing `id: "root"` or multiple disconnected root widgets render properly instead of displaying a blank panel.
2. Provide actionable warnings back to the agent in the tool response when incomplete component structures are statically detected.
3. Update the bundled A2UI skills to prominently teach the mandatory root component convention and provide comprehensive examples.

## Decision

1. **Auto-Synthesis of Root Container in Component Normalization**:
   - In both Python (`normalize_a2ui_components` in `seamus.harness.artifacts`) and TypeScript (`normalizeComponents` in `ui/src/components/A2UIArtifactRenderer.tsx`):
     - Check if any component in the tree has `id: "root"`.
     - If no component has `id: "root"`:
       - Identify all top-level root candidates (components not referenced as `child`, `children`, `trigger`, `content`, or `tabs` by any other component).
       - If root candidates exist, synthesize and prepend a `Column` container:
         ```json
         {
           "id": "root",
           "component": "Column",
           "children": ["<candidate_1>", "<candidate_2>", ...]
         }
         ```
     - This guarantees that existing and newly authored artifacts with disconnected top-level widgets always mount and render visibly in the UI.

2. **Static Incomplete Structure Warning**:
   - Add `check_a2ui_surface_warnings(components)` in `seamus.harness.artifacts`.
   - Statically flags:
     - Missing explicit `id: "root"` component.
     - Multiple disconnected top-level widgets.
     - Orphaned components (components not reachable from the root component).
   - When `handle_make_artifact` in `seamus.harness.runner` creates an artifact with incomplete structure:
     - The artifact is stored and broadcast (using the normalized/auto-wrapped components).
     - The tool response returns the created artifact UUID together with the static warning and instructions for declaring an explicit root container.

3. **Bundled Skill Enhancements**:
   - Update `src/seamus/skills/bundled/a2ui_components/SKILL.md` and `src/seamus/skills/bundled/artifacts/SKILL.md`:
     - Document that A2UI strictly requires a root container with `"id": "root"`.
     - Show the single-tree hierarchy pattern from `root` down to leaf widgets.
     - Detail common pitfalls: omitting root, multiple disconnected roots, inline nested components, and `Card`/`Button` property constraints.

## Consequences

- Artifacts authored without an explicit `"root"` ID no longer produce blank panels in the UI; they render cleanly inside an auto-synthesized root `Column`.
- Agents receive clear static warnings informing them that their component tree was missing `"root"` and explaining how to structure future artifacts.
- The bundled skills provide clear, unambiguous guidance for authoring well-formed A2UI surfaces.

