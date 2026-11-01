# 0020. Logfire Telemetry Configuration Parameterization and Prompt Scrubbing Exemption

Date: 2026-11-01

## Status

Accepted

## Context

Two distinct telemetry shortcomings were identified in Seamus:
1. **Hardcoded Logfire Cloud Region and Organization**: In `src/seamus/server/routes/system.py` and `ui/src/components/Sidebar.tsx`, the Logfire dashboard link was hardcoded to `https://logfire-eu.pydantic.dev/filip-malczak/{service_name}`, preventing portability across different organizations, user accounts, and Logfire cloud endpoints.
2. **False-Positive System Prompt Scrubbing**: In Logfire spans capturing model calls, system prompts were redacted with `[Scrubbed due to 'auth']`. Logfire's built-in credential scrubber pattern `auth(?!ors?\b)` matched the word `"authoring"` in `build_engineering_discipline()` (*"before authoring code"*) and would similarly match words derived from `author` (e.g. `authoring`, `authored`, `authorship`), redacting the entire prompt payload.

## Decision

1. **Parameterize Logfire Dashboard Link**:
   - Introduce `LOGFIRE_ORG` and `LOGFIRE_BASE_URL` in `src/seamus/telemetry.py` and document them in `.env.template`.
   - Provide helper functions `get_logfire_org()`, `get_logfire_base_url()`, and `get_logfire_dashboard_url()` dynamically generating the URL when configured.
   - Update `src/seamus/server/routes/system.py` to populate `SystemInfoResponse.logfire.url` from `get_logfire_dashboard_url()`.
   - Update `ui/src/components/Sidebar.tsx` to use the dynamic URL returned from the API rather than hardcoded URLs.

2. **Exempt Author-Derived False Positives from Redaction**:
   - Update `_scrub_callback` in `src/seamus/telemetry.py` to check `auth` matches: if the matched substring is part of a word starting with `author` (`^author\w*`), preserve the value rather than redacting it. Genuine authentication tokens and keys remain scrubbed.
   - Refine `build_engineering_discipline()` in `src/seamus/harness/prompt.py` to use `"before writing code"` instead of `"before authoring code"` for defensive redundancy.

## Consequences

### Positive
- Deployments can point Logfire dashboard links to arbitrary accounts and cloud endpoints via environment variables without code modification.
- System prompts are clearly visible in Logfire traces without losing genuine credential scrubbing protection.
- Frontend sidebar links dynamically respect server-provided configuration.

### Negative / Trade-offs
- If `LOGFIRE_ORG` is unset, `SystemInfoResponse.logfire.url` is `None`, and the sidebar link falls back to the generic `https://logfire.pydantic.dev` home page.
