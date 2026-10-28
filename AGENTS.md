# Seamus

## Vision

A deep agent harness that I fully own and can customize. 

## General

* Do not rewrite unrelated code or implement future functionality unless required by the task.
* When uncertain about architecture, ask rather than invent one.
* Prefer simple, explicit solutions over speculative abstractions.
* Keep framework concerns separate from application/harness concerns.
* Document every architectural or project-direction decision in `./decisions/`, following these rules:
  * Append-only: create new Markdown files; never modify existing entries unless explicitly instructed or superseding them.
  * Prefix filenames with four-digit numbers.
  * To supersede an entry, rename it by inserting `SUPERSEDED` between its number and slug; add or update a top-level Markdown quote linking to the superseding entry. Limit modifications to the rename and top comment. Multiple superseding entries are allowed and must all be linked. Superseded entries may remain partially valid.
* Store durable, non-decision implementation knowledge in `./knowledge/`. Keep files focused, cross-link related concepts and decisions to preserve provenance, and follow the documented terminology and abstraction conventions.
* Neither directory is for temporary notes, scratch work, or investigation debris.

## Planning Agents

For autonomous agents without explicit Plan/Act modes, plan unless the task is trivial; explain why when skipping a plan.

In **Plan** mode:
* Never execute without explicit approval (normally **Proceed** or switching to **Act**).
* Review is not approval. If approval is unclear, assume it was not given.

## Git

### Repository State

* Never perform feature work directly on `master`; each task gets its own feature branch.
* If a task starts outside `master`, stop and ask whether to switch to `master` and branch from there, or deliberately continue on the current branch. Do not assume which is intended.

### Feature Branches

Before implementation:

1. Inspect existing decision-log filenames and all local and remote branches to identify numbers already in use. A number is occupied if it appears in either place, even if no corresponding decision-log entry exists.
2. Identify the relevant decision-log entry. If a new entry is needed, assign it an unused number.
3. Use the relevant entry's four-digit number as the feature branch prefix.
4. Create the branch from the current `master`.

Format: `NNNN-short-task-description` (e.g. `0001-repository-structure`, `0002-v0-harness`, `0003-persistent-runs`). Never reuse a number already assigned to an existing decision entry or branch, or reuse a branch for an unrelated task.

### Review and Merge

Workflow: `master → NNNN-feature → implementation → tests → verification → user review → approved merge`.

* Never merge before user review and approval.
* After approval, merge into `master` without squashing or rewriting history unless explicitly requested; leave the repository on `master` unless instructed otherwise.
* For post-review changes, continue on the existing feature branch unless a new task is explicitly defined.
* Never delete past task branches unless asked.

### Commits

* Never commit unless explicitly instructed or an approved plan explicitly includes the commit. If a commit would otherwise be appropriate, stop and ask.
* When requesting commit approval, state the proposed commit message and included files.
* Explicit authorization of the task's normal Git workflow authorizes its required commits.
* Never overwrite manual user changes.

### Staging

* Stage all production files created or modified for the task and everything under `./knowledge/`.
* Never stage scratch, experimental, temporary, or investigation files.
* Leave the repository ready to commit.

## Python

### Environment and Dependencies

* Use Python 3.12 and `uv` for project and dependency management.
* Keep `pyproject.toml` and `uv.lock` consistent.
* Prefer `uv add` / `uv remove` for dependency changes and `uv run` for project commands.
* Do not introduce another environment or dependency manager without approval.

### Code and Tooling

* Prefer idiomatic Python, explicit boundaries where they improve readability or testability, and type annotations on public interfaces and non-trivial code.
* Keep modules small and cohesive; avoid unnecessary abstraction layers.
* Do not suppress lint or type-checker findings without a documented reason.
* Use Ruff for linting and formatting, mypy for type checking, and pytest for testing.
* Keep tool configuration in `pyproject.toml` and run verification through `uv run`.

## Testing

* Tests are part of implementation, not an afterthought. Run relevant subsets during development and the established full test, lint, type-check, and format checks before completion.
* Do not finish while any check fails.
* Never remove or weaken tests without explicit approval.
* Prefer testing observable behavior and meaningful boundaries over implementation details.

## Code Organization

* Keep modules focused; do not reorganize existing code for aesthetics alone.
* Give new subsystems clear package boundaries and document important architectural decisions in `./decisions/`.
* Follow package organization conventions in `./knowledge/abstractions.md`.

## Documentation

Keep `AGENTS.md` focused on repository-wide working rules, not project design. Task-specific requirements and detailed implementation plans belong in the task prompt or appropriate project documentation.

Use:
* `./decisions/` for architectural and project-direction decisions.
* `./knowledge/` for durable implementation knowledge.

Maintain these knowledge files:

* `vocabulary.md` — canonical terms, definitions, and distinctions.
* `requirements.md` — requirements, rationale, provenance, and stable IDs (e.g. `REQ-001`).
* `invariants.md` — properties that must always hold, linked to the requirements or other sources that justify them.
* `architecture.md` — components, responsibilities, dependencies, and data flows.
* `abstractions.md` — interfaces, protocols, ABCs, implementations, package boundaries, and extension points.
* `conventions.md` — project-specific implementation conventions not already enforced by tooling.

Cross-link related concepts across knowledge files and to relevant decision entries. Preserve traceability from requirements through invariants, architecture, abstractions, implementation, and tests where applicable.

Keep knowledge synchronized with the implementation:
* Update `abstractions.md` when documented contracts, implementations, or extension points change.
* Update `requirements.md` and `invariants.md` when affected behavior changes, including relevant cross-references.
* Update other knowledge files when documented concepts or relationships change.
* Document only information whose absence would materially hinder future work or increase errors. Do not duplicate source code or document every class and function.

## Final Task Checklist

Before declaring a task complete:

* [ ] Correct numbered feature branch, with its number checked against decision filenames and all local and remote branches.
* [ ] Architectural decisions recorded in `./decisions/`.
* [ ] Durable implementation knowledge documented where appropriate.
* [ ] Relevant knowledge files and decisions cross-linked.
* [ ] Knowledge updated to reflect implementation changes.
* [ ] No unrelated code rewritten.
* [ ] Tests pass.
* [ ] Ruff linting and formatting checks pass.
* [ ] mypy type checking passes.
* [ ] Production changes and all `./knowledge/` changes staged; scratch files unstaged.
* [ ] Repository ready for user review.
* [ ] No merge into `master` before user review and approval.
