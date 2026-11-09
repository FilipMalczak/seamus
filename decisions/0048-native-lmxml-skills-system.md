# 0048. Native LM-XML Skills System with Explicit Load/Unload Tools

Date: 2026-11-09

## Status

Accepted

## Context

Anthropic agent skills (`SKILL.md`) were previously integrated via LangChain DeepAgents' built-in `SkillsMiddleware` ([0024-anthropic-skills-and-system-settings.md](./0024-anthropic-skills-and-system-settings.md), [0026-in-sandbox-skill-mount-paths.md](./0026-in-sandbox-skill-mount-paths.md), [0027-skills-config-project-rules-and-inspector.md](./0027-skills-config-project-rules-and-inspector.md), [0047-discovered-context-and-project-skills.md](./0047-discovered-context-and-project-skills.md)).

However, `SkillsMiddleware` suffered from fundamental architectural limitations:
1. **Rigid System Prompt Appending**: Injected flat markdown strings into the system message rather than conforming to Seamus's structured LM-XML system prompt architecture ([0018-dynamic-system-prompt-architecture.md](./0018-dynamic-system-prompt-architecture.md)).
2. **Implicit Disclosure via Tool Call Snooping**: Relied on intercepting `read_file` tool calls on `SKILL.md` paths to disclose tool dependencies, permanently dumping verbose markdown instructions into the chat message history where they permanently bloated the context window.
3. **Fragile Frontmatter Parsing**: PyYAML parsing silently dropped valid skills with unquoted inline structures (such as colons or braces in descriptions, e.g. `bevy-assets`).
4. **Lack of Lifecycle Control**: Agents had no mechanism to unload skills once a specialized task concluded, preventing context window token reclamation.

## Decision

1. **Implementation-Agnostic Discovery & Precedence Hierarchy (INV-035)**:
   - Consolidate skill discovery into `src/seamus/harness/skills.py` (`discover_session_skills`).
   - Standardize discovery order and precedence rules so that `seamus`, `deepagents`, and the Agent Inspector discover and shadow skills identically:
     `Bundled` > `Session (/workspace/skills)` > `Session (/workspace/.skills)` > `Project 0 (skills)` > `Project 0 (.skills)` > ... > `System 0` > `System 1`.
   - The first match for any skill name wins (`active=True`); subsequent matches are marked shadowed (`active=False`).

2. **Resilient Frontmatter Parser**:
   - Provide `parse_skill_markdown()` handling unquoted colons, JSON-like braces, multiline folded/literal descriptions, and tool dependency lists (`allowed_tools: [...]` or `- tool`) without YAML parser crashes.

3. **LM-XML Dynamic Prompt Serialization**:
   - Model available and active skills using pure element tag trees in `src/seamus/harness/prompt.py` (`SystemPromptDocument`, `SkillsPromptDocument`, `AvailableSkillPromptItem`, `ActiveSkillPromptItem`).
   - In accordance with LM-XML capabilities, all properties serialize as pure child elements without XML attributes:
     `<skills><available_skills><list><item index="0"><name>...</name><description>...</description></item></list></available_skills><active_skills><list><item index="0"><name>...</name><instructions>...</instructions></item></list></active_skills><guidelines>...</guidelines></skills>`.
   - When no skills are loaded, `<active_skills>` is omitted cleanly. When no skills exist across sources, `<skills>` is omitted entirely.

4. **SeamusSkillsMiddleware and Explicit Load/Unload Tools**:
   - Implement `SeamusSkillsMiddleware(AgentMiddleware)` registering two first-party agent tools:
     - `load_skill(name: str) -> str`: Validates the skill against available unshadowed skills, appends it to `thread.active_skills`, unlocks declared `allowed_tools`, and returns an activation message.
     - `unload_skill(name: str) -> str`: Removes the skill from `thread.active_skills`, revoking associated tools and freeing context tokens.
   - When `skills_implementation == SkillsImplementation.SEAMUS`, pass `skills=None` to `create_deep_agent` to bypass DeepAgents' `SkillsMiddleware` completely.

5. **Thread-Scoped Active Skills**:
   - Store `active_skills: list[str] = Field(default_factory=list)` on `Thread` in `src/seamus/domain/entities.py`.
   - Thread scoping ensures loaded skills persist across turns and Gitea commits, while operational mode switches and fresh thread transitions start with a clean context.

6. **Configuration Default & UI Observability**:
   - Add `SkillsImplementation.SEAMUS = "seamus"` and set it as the default across `AgentConfig`. Retain `deepagents` and `none` for backward compatibility.
   - Surface a `Loaded` badge on active skills in `AgentInspector.tsx` and show associated tools in the Inspector preview.
   - Record a backlog item to support skill stashing across thread transitions.

## Consequences

### Positive
- Strict alignment with Seamus's structured LM-XML system prompt architecture.
- Agents explicitly manage their own context window budgeting using `load_skill` and `unload_skill`.
- Resilient YAML frontmatter parsing eliminates dropped real-world skills.
- Tool dependencies declared via `allowed_tools` are gated until skill activation.
- Discovery ordering and layer precedence are unified and implementation-agnostic across all modes.

### Negative / Trade-offs
- The model must expend a tool call turn to invoke `load_skill` rather than reading the file directly via `read_file`.

