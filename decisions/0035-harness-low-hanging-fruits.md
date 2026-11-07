# 0035: Harness Usability, Artifact Lifecycles, and Conversational Continuity (Low-Hanging Fruits)

- **Date**: 2026-11-07
- **Status**: Accepted
- **Supersedes**: None

## Context

Following the maturation of the A2UI artifacts model in [0034-mature-a2ui-artifacts-model.md](./0034-mature-a2ui-artifacts-model.md) and backlog organization, several concrete friction points across daily usage, agent reasoning, and state management were identified as high-value, low-effort improvements ("low-hanging fruits"):

1. **Lingering `gpt-oss-20b` Default**: Clean resets (`./run.sh --clean`) and frontend presets still surfaced the 20b model (e.g. in `.env`, `ConfigModal.tsx`), which was too small and unreliable for agentic tool calling.
2. **Composer Freezing During Agent Turns**: In the chat area, active agent processing or open blocking artifacts locked the entire `<textarea>` input element, preventing users from drafting follow-up messages while the agent worked.
3. **Artifact Button Disappearance on Close**: Closing artifacts caused proceed and submit buttons to vanish from the card render rather than remaining visible in a disabled state, due to configuring `clicks=1` (causing click count exhaustion to 0).
4. **Git Pollution and Persistence Ambiguity**: Newly created agent workspaces lacked a default `.gitignore`, risking repository pollution from `venv` or `node_modules`, and system prompts lacked explicit guidance on how `.gitignore` dictates Git persistence boundaries.
5. **Thread Navigation Loss on Accept**: When accepting a thread (Sync PR merge) in the Changes viewer, the UI failed to automatically select and navigate to the newly created child thread, leaving the user stranded on the closed historical thread.
6. **Conversational Amnesia Across Thread Rollover**: Spawning a child thread (e.g. when switching modes or rolling over threads) started execution with zero conversational history in the checkpoint, breaking immediate conversational continuity.

## Decisions

### 1. Complete Purge of `gpt-oss-20b`
- Updated `.env` and `.env.template` to set `OPENROUTER_MODEL=openai/gpt-oss-120b`.
- Removed `"openai/gpt-oss-20b"` from `MODEL_PRESETS` in `ConfigModal.tsx`.
- Standardized all test descriptions and comments to eliminate 20b references.

### 2. Decoupled Composer Input Editability
- In `ChatArea.tsx`, the composer `<textarea>` remains enabled while the active thread is open (`disabled={!isOpen}`), regardless of whether the agent is busy or a blocking artifact is open.
- The Send button and Enter key submission handler remain strictly disabled when `isBusy || sending || hasOpenBlockingArtifact`, preventing premature dispatch while allowing the user to draft upcoming prompts.
- Placeholder text dynamically informs the user that drafting is permitted while the agent is busy or awaiting questionnaire submission.

### 3. Button Retention via Unlimited Clicks (`clicks="*"`)
- In `src/seamus/harness/artifacts.py`, artifact builders (`QuestionnaireBuilder`, `FormBuilder`, and `PlanBuilder`) configure submission and proceed buttons with default `clicks="*"` instead of `clicks=1`.
- Removed explicit click exhaustion overwriting (`clicks["proceed-btn"] = 0`) in `PlanBuilder.approve_plan`.
- Completion and interaction prevention are governed strictly by artifact closure (`closed.marker` and `is_closed` disabled state in the UI) rather than click quota exhaustion, ensuring buttons remain visible in a disabled state after closure.

### 4. Standard `.gitignore` Seeding and Prompt Persistence Guidance
- `GitWorkspaceManager.initialize_agent_repo` seeds a comprehensive `.gitignore` (ignoring `__pycache__`, virtual environments, `node_modules`, build/dist directories, and log files) and commits it to `main` upon agent creation.
- In `src/seamus/harness/prompt.py`, `build_operating_environment` appends explicit guidance to the agent that `.gitignore` governs Git tracking and persistence, whereas ignored and untracked files remain ephemeral within the sandbox container.

### 5. Automatic UI Navigation on Thread Creation and Acceptance
- In `App.tsx`, `onAcceptThread` captures the newly spawned thread returned by `acceptThread(...)`, invokes `selectThread(agentId, sessionId, newThread.id)`, and switches the active main tab back to `"chat"`.
- Mode transitions and backend `THREAD_TRANSITION` events consistently steer active view selection to the destination open thread.

### 6. Configurable Conversational Message Overlap Across Threads
- Added `thread_message_overlap: int = 5` to `AgentConfig`, configurable via `SEAMUS_THREAD_MESSAGE_OVERLAP` environment variable and inherited across entity hierarchies.
- In `SessionAgentRunner`, when starting execution on an empty thread that succeeds a prior thread in the same session, `_seed_thread_overlap` extracts the trailing $N$ messages from the predecessor thread via `graph.get_state` and seeds them into the new thread via `graph.update_state`.
- Added `select_message_overlap` helper to ensure the message slice never starts on an orphaned `ToolMessage`, walking backward to include the triggering assistant message or trimming orphaned tools.

## Consequences

- Clean system starts reliably point to capable frontier models without 20b regressions.
- Conversational UX feels fluid and non-blocking, permitting prompt drafting at all times.
- Completed questionnaires, forms, and approved plans retain their interactive buttons in a clean, disabled historical state.
- Repository persistence remains lean and clean from transient caches and virtual environments.
- Accepting Sync PRs and switching modes seamlessly keeps the operator on the cutting edge of the conversation.
- Agents retain vital conversational context across thread transitions without requiring manual recap prompts.

