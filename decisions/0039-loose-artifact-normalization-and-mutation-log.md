# 0039 Loose Artifact Normalization and Mutation Log

- **Status**: Accepted
- **Date**: 2026-11-07
- **Authors**: Filip, DeepMind Pair Assistant
- **Deciders**: Filip, Seamus Harness Core Team
- **Consulted**: Seamus Harness Core Team
- **Informed**: Seamus Developer Community

## Context and Problem Statement

When LLM agents invoke `make_artifact` to generate custom interactive A2UI surfaces, slight syntax or convention deviations frequently trigger hard validation rejections, rejecting artifact persistence and causing costly, repetitive conversational roundtrips.

Empirical evaluation of agent sessions reveals that the two most common error classes are:
1. `Component at index X is missing a non-empty string 'id'.`
   When an agent emits purely informational components (e.g. descriptive paragraphs, headings, separators), it often omits the `id` property because it does not intend to refer to or bind state to the widget. Demanding that the LLM perform an extra turn merely to assign unused arbitrary IDs adds friction and context token churn.
2. `Component 'X' is missing a valid 'component' type.`
   Agents frequently use common JSON schema conventions such as `"type"`, `"component_type"`, `"componentType"`, `"widget"`, or lowercase/short aliases (e.g. `"text"`, `"button"`, `"heading"`), or embed properties directly without explicit envelope keys.

Furthermore, when agents provide `Button` components without declaring them in `manifest.buttons`, or author `Card` containers with inline `title`/`body`/`children` rather than dedicated single-child subtrees, rigid validators fail the render check.

Where semantic intent can be reliably deduced, Seamus should normalize the payload rather than fail and prompt the LLM. Crucially, the harness must return a comprehensive log of these mutations to the agent so that it not only receives the artifact ID, but clearly understands how its request was mutated.

## Decision Drivers

- **Fault Tolerance & Resilience**: Intelligently resolve obvious semantic intent (missing IDs, component type aliases, casing, button child synthesis, undeclared manifest buttons) instead of failing.
- **Roundtrip Reduction**: Prevent unnecessary LLM retries for trivial syntax oversights.
- **Agent Transparency**: Explicitly return a structured mutation log to the agent in the `make_artifact` tool response detailing all automatic adaptations.
- **Frontend & Backend Symmetry**: Ensure Python and TypeScript normalizers share the same loose parsing and adaptation rules.
- **Zero Invalidation of Explicit Syntax**: Strict, valid A2UI payloads must pass through unmodified with empty mutation logs.

## Considered Options

1. **Option 1: Strict Validation with Instructional Error Messages**
   Keep `validate_a2ui_surface` strict; when an ID is missing or `type` is used, return detailed hints instructing the agent how to fix it.
   - *Pros*: Keeps normalizer code minimal.
   - *Cons*: Guaranteed multi-turn roundtrip penalty for trivial formatting quirks; worsens latency and LLM context bloat.

2. **Option 2: Loose Normalization with Silent Adaptation**
   Silently adapt missing IDs and aliases without reporting mutations back to the agent.
   - *Pros*: Creates artifacts immediately.
   - *Cons*: Violates agent transparency. The agent might attempt to interact with or reference component IDs or hierarchy assumptions that were rewritten under the hood without its knowledge.

3. **Option 3 (Selected): Loose Normalization with Explicit Mutation Log Feedback**
   Perform loose normalization prior to validation:
   - Auto-assign deterministic unique IDs for components missing `id`.
   - Auto-rename `type`, `component_type`, `componentType`, `widget`, `kind` to `component`, and normalize casing/aliases.
   - Auto-infer component types from distinctive properties (e.g. `text` -> `Text`, `options` -> `ChoicePicker`).
   - Synthesize child `Text` components for `Button` instances when `label` or `text` is supplied directly.
   - Adapt `Card` instances with `title`/`body`/`children` into standard single-child `Column` subtrees.
   - Auto-declare undeclared buttons in `manifest.buttons`.
   - Auto-synthesize root `Column` container if missing.
   - Return the artifact UUID alongside a structured `Notice: Automatically normalized component tree:` log in the tool output.

## Decision Outcome

Option 3 was chosen.

### Normalization Details

1. **Component ID Auto-Assignment**:
   - Inspect components missing a non-empty string `id`.
   - Assign deterministic IDs prefixed by lowercase component type (e.g. `text_0`, `button_1`, `comp_2`), ensuring collision avoidance against already declared IDs.
   - Log mutation: `Auto-assigned id='<id>' to component at index <idx> (missing ID)`.

2. **Component Type Aliases and Inference**:
   - Rename `type`, `component_type`, `componentType`, `widget`, `kind` to `component`.
   - Map canonical component names case-insensitively (`text` -> `Text`, `button` -> `Button`, `column` -> `Column`, `row` -> `Row`, `card` -> `Card`, `divider` -> `Divider`, `image` -> `Image`, `heading`/`header` -> `Text` with `variant: "h2"`).
   - Infer component types from distinctive properties if `component` is missing (`text` -> `Text`, `children` -> `Column`, `options`/`choices` -> `ChoicePicker`, `url`/`src` -> `Image`, `tabs` -> `Tabs`, `action` -> `Button`).

3. **Button and Card Simplifications**:
   - For `Button`, if `child` is omitted and `label` or `text` is provided, synthesize a child `Text` component and link `child` to its ID.
   - For `Card`, if `child` is omitted but `title`, `body`, or `children` are supplied, synthesize a content `Column` enclosing them and set `child` to its ID.

4. **Manifest Button Alignment**:
   - If a `Button` exists in components but is omitted from `manifest.buttons`, auto-declare a corresponding `ManifestButton` in `manifest.buttons`.

5. **Mutation Log Transparency**:
   - `handle_make_artifact` returns:
     ```text
     <uuid>

     Notice: Automatically normalized component tree:
     - Auto-assigned id='text_0' to component at index 0 (missing ID).
     - Renamed 'type' ('Text') to 'component' on component 'intro'.

     Warning: Incomplete A2UI component tree:
     - ...
     ```

## Consequences

### Positive
- Common minor mistakes no longer block artifact creation or cause extra LLM turns.
- Agents receive immediate, educational feedback on how their payload was normalized, helping them learn correct conventions while keeping tasks moving forward.
- Both frontend and backend render pipelines reliably handle loose representations.

### Negative / Trade-offs
- The normalizer contains heuristic inference logic that must be maintained and kept synchronized across Python and TypeScript.
- Tests must explicitly account for loose auto-repair behavior.

## Pros and Cons of the Options

### Strict Validation (Option 1)
- Good: Minimal backend code.
- Bad: Poor developer and agent ergonomics; high turn latency.

### Loose Normalization with Explicit Feedback (Option 3)
- Good: Maximum resilience with full conversational transparency.
- Good: Zero agent roundtrip overhead for harmless omissions.
- Bad: Normalizer complexity increases.

## Links

- [0037 Pre-Render A2UI Surface Validation](../decisions/0037-validate-a2ui-surface-render-on-make-artifact.md)
- [0038 A2UI Root Component and Incomplete Structure Warning](../decisions/0038-a2ui-root-component-and-incomplete-structure-warning.md)
- [Artifact Subsystem Durable Knowledge](../knowledge/artifacts.md)
- [System Requirements](../knowledge/requirements.md)
- [System Invariants](../knowledge/invariants.md)

