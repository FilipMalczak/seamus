"""Autocontinue daemon for automated session failure evaluation and retry branching."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from seamus.domain.artifacts import SYNTHETIC_MESSAGE_INDICATOR
from seamus.harness.daemons.engine import invoke_daemon
from seamus.harness.daemons.formatter import format_thread_history
from seamus.harness.daemons.naming import _resolve_daemon_api_key
from seamus.harness.steerable import daemon_instance_id

if TYPE_CHECKING:
    from seamus.domain.entities import Session, Thread
    from seamus.harness.runner import SessionAgentRunner

logger = logging.getLogger(__name__)

AUTOCONTINUE_INSTRUCTIONS = (
    "You are an expert execution supervisor and autocontinue daemon.\n"
    "Analyze the provided recent conversation messages, failure details (error type, message,\n"
    "traceback), and retry/error history for this agent session, and determine whether it makes\n"
    "sense to retry execution.\n\n"
    "Guidelines:\n"
    "- Reply 'yes' (or 'true') if the failure appears transient, intermittent, or recoverable\n"
    "  (e.g. temporary timeout, momentary network glitch, transient tool execution hiccup,\n"
    "  recoverable API error, temporary rate limit).\n"
    "- Reply 'no' (or 'false') if the failure is unrecoverable, permanent, or external\n"
    "  (e.g. running out of credits or depleted balance, quota permanently exhausted, network\n"
    "  completely down or host unreachable, invalid credentials / 401 unauthorized, model\n"
    "  unavailable or deprecated, syntax errors, or if frequent/repeated retries have already\n"
    "  occurred across spans or lineage and further retries should not be attempted).\n\n"
    "Requirements:\n"
    "- Output: Print ONLY 'yes' or 'no'.\n"
    "- Do NOT add markdown, quotes, explanations, or extra punctuation."
)


def parse_autocontinue_response(raw_output: str | None) -> bool:
    """Parse loose LLM output into a boolean indicating whether to retry execution.

    Accepts 'yes', 'true', '1', 'retry', 'y', 't' (case-insensitive, stripped).
    Returns False on 'no', 'false', '0', empty/None, or any other response.
    """
    if not raw_output:
        return False

    cleaned = raw_output.strip().lower()
    for char in ('"', "'", "`", "*", ".", "!", ";", ",", ":"):
        cleaned = cleaned.replace(char, " ")
    tokens = cleaned.split()
    if not tokens:
        return False

    first_token = tokens[0]
    if first_token in ("yes", "true", "1", "retry", "y", "t"):
        return True

    if any(tok in ("yes", "true", "1", "retry") for tok in tokens) and not any(
        tok in ("no", "false", "0", "dont", "stop", "never") for tok in tokens
    ):
        return True

    return False


def find_last_successful_bubble(thread: Thread) -> tuple[str, str] | None:
    """Locate the last fully successful bubble (message, reasoning span, tool call set) in thread.

    Returns a tuple of (target_id, item_type) suitable for branching via store.branch_session.
    """
    events = thread.events
    if not events:
        return None

    def ev_attr(ev: Any, attr: str) -> Any:
        return getattr(ev, attr, None) or (ev.get(attr) if isinstance(ev, dict) else None)

    # 1. Identify all completed successful tool groups
    tool_records: list[dict[str, Any]] = []
    tool_by_id: dict[str, dict[str, Any]] = {}
    for idx, ev in enumerate(events):
        t_type = str(ev_attr(ev, "type") or "").upper()
        tcid = ev_attr(ev, "tool_call_id") or (
            ev_attr(ev, "id") if t_type.startswith("TOOL_CALL") else None
        )
        if tcid:
            tcid_str = str(tcid)
            if tcid_str not in tool_by_id:
                rec = {
                    "tool_call_id": tcid_str,
                    "start_idx": idx,
                    "end_idx": idx,
                    "result_idx": None,
                    "is_error": False,
                }
                tool_by_id[tcid_str] = rec
                tool_records.append(rec)
            else:
                rec = tool_by_id[tcid_str]

            if t_type == "TOOL_CALL_RESULT":
                rec["result_idx"] = idx
                if ev_attr(ev, "is_error"):
                    rec["is_error"] = True
            else:
                rec["end_idx"] = idx

    tool_groups: list[list[dict[str, Any]]] = []
    for trec in tool_records:
        if not tool_groups:
            tool_groups.append([trec])
        else:
            last_group = tool_groups[-1]
            prev_res = max(
                (t["result_idx"] for t in last_group if t["result_idx"] is not None),
                default=None,
            )
            if prev_res is None or trec["start_idx"] <= prev_res:
                last_group.append(trec)
            else:
                tool_groups.append([trec])

    # 2. Identify all completed user messages
    user_records: list[dict[str, Any]] = []
    curr_user: dict[str, Any] | None = None
    for idx, ev in enumerate(events):
        e_type = str(ev_attr(ev, "type") or "").upper()
        role = str(ev_attr(ev, "role") or "").lower()
        is_user_start = (
            e_type in ("USER_INPUT",)
            or (role == "user" and e_type in ("TEXT_MESSAGE_START",))
            or (
                role == "user"
                and not curr_user
                and e_type not in ("RUN_STARTED", "RUN_FINISHED", "RUN_ERROR")
            )
        )
        if is_user_start:
            if curr_user is not None:
                user_records.append(curr_user)
            mid = ev_attr(ev, "message_id") or ev_attr(ev, "id") or f"user-{len(user_records)}"
            delta = str(ev_attr(ev, "delta") or ev_attr(ev, "text") or ev_attr(ev, "content") or "")
            curr_user = {
                "message_id": str(mid),
                "start_idx": idx,
                "end_idx": idx,
                "is_synthetic": SYNTHETIC_MESSAGE_INDICATOR in delta,
            }
            continue
        if curr_user is not None:
            curr_mid = str(ev_attr(ev, "message_id") or "")
            if curr_mid == curr_user["message_id"] or role == "user":
                curr_user["end_idx"] = idx
            elif e_type in ("RUN_STARTED", "TEXT_MESSAGE_START") or role in ("assistant", "system"):
                user_records.append(curr_user)
                curr_user = None
    if curr_user is not None:
        user_records.append(curr_user)

    # 3. Identify completed reasoning blocks
    reasoning_records: list[dict[str, Any]] = []
    curr_reasoning: dict[str, Any] | None = None
    for idx, ev in enumerate(events):
        e_type = str(ev_attr(ev, "type") or "").upper()
        if "REASONING" in e_type:
            rid = (
                ev_attr(ev, "message_id")
                or ev_attr(ev, "id")
                or f"reasoning-{len(reasoning_records)}"
            )
            rid_str = str(rid)
            if curr_reasoning is None:
                curr_reasoning = {
                    "id": rid_str,
                    "start_idx": idx,
                    "end_idx": idx,
                }
            else:
                curr_reasoning["end_idx"] = idx
        else:
            if curr_reasoning is not None:
                reasoning_records.append(curr_reasoning)
                curr_reasoning = None
    if curr_reasoning is not None:
        reasoning_records.append(curr_reasoning)

    # 4. Identify completed bot text messages
    bot_text_records: list[dict[str, Any]] = []
    curr_bot: dict[str, Any] | None = None
    for idx, ev in enumerate(events):
        e_type = str(ev_attr(ev, "type") or "").upper()
        role = str(ev_attr(ev, "role") or "").lower()
        mid = str(ev_attr(ev, "message_id") or ev_attr(ev, "id") or "")
        if role == "assistant" and "TEXT_MESSAGE" in e_type:
            mid_str = mid or f"asst-text-{len(bot_text_records)}"
            if curr_bot is not None and curr_bot["message_id"] != mid_str:
                bot_text_records.append(curr_bot)
                curr_bot = None
            if curr_bot is None:
                curr_bot = {
                    "message_id": mid_str,
                    "start_idx": idx,
                    "end_idx": idx,
                }
            else:
                curr_bot["end_idx"] = idx
        elif curr_bot is not None:
            if mid == curr_bot["message_id"] or "TEXT_MESSAGE" in e_type:
                curr_bot["end_idx"] = idx
            elif e_type in ("RUN_FINISHED", "RUN_ERROR"):
                curr_bot["end_idx"] = idx
                bot_text_records.append(curr_bot)
                curr_bot = None
            else:
                bot_text_records.append(curr_bot)
                curr_bot = None
    if curr_bot is not None:
        bot_text_records.append(curr_bot)

    # Locate first unhandled RUN_ERROR index in events to know where the fatal failure hit
    fatal_error_idx = len(events)
    for idx, ev in enumerate(events):
        if str(ev_attr(ev, "type") or "").upper() == "RUN_ERROR":
            fatal_error_idx = idx
            break

    # Build candidates: (end_idx, target_id, item_type)
    candidates: list[tuple[int, str, str]] = []

    # Completed tool groups (all tools must have completed without error before fatal error)
    for group in tool_groups:
        all_completed = all(t["result_idx"] is not None for t in group)
        no_error = not any(t["is_error"] for t in group)
        if all_completed and no_error:
            last_res = max(t["result_idx"] for t in group if t["result_idx"] is not None)
            if last_res < fatal_error_idx:
                rep_id = group[0]["tool_call_id"]
                candidates.append((last_res, rep_id, "tool_call"))

    # Completed reasoning blocks
    for rrec in reasoning_records:
        if rrec["end_idx"] < fatal_error_idx:
            candidates.append((rrec["end_idx"], rrec["id"], "bot_thinking"))

    # Completed bot text messages
    for brec in bot_text_records:
        if brec["end_idx"] < fatal_error_idx:
            candidates.append((brec["end_idx"], brec["message_id"], "bot_message"))

    # Completed user messages
    for urec in user_records:
        if urec["end_idx"] < fatal_error_idx:
            itype = "system_event" if urec["is_synthetic"] else "user_message"
            candidates.append((urec["end_idx"], urec["message_id"], itype))

    if not candidates:
        return None

    # Pick the candidate bubble with the highest event index before the fatal failure
    candidates.sort(key=lambda c: c[0])
    _, target_id, item_type = candidates[-1]
    return target_id, item_type


def _format_autocontinue_payload(
    runner: SessionAgentRunner,
    thread: Thread,
    exc: Exception | None,
    err_event: dict[str, Any],
) -> str:
    """Format short recent messages, specific failure details, and lineage/retry history."""
    # 1. Recent short conversation messages
    history_text = format_thread_history(thread.events)

    # 2. Failure details
    err_type = err_event.get("error_type") or (type(exc).__name__ if exc else "UnknownError")
    err_msg = err_event.get("message") or (str(exc) if exc else "No error message provided.")
    tb = err_event.get("traceback") or ""
    tb_snippet = tb.strip().splitlines()
    if len(tb_snippet) > 8:
        tb_snippet = tb_snippet[:4] + ["    ... [truncated] ..."] + tb_snippet[-4:]
    formatted_tb = "\n".join(tb_snippet) if tb_snippet else "(no traceback available)"

    # 3. Lineage & retry frequency history from latest span and ancestor chain
    lineage = runner.session.lineage or []
    lineage_depth = len(lineage)
    prov = runner.session.provenance
    prior_session_id = str(prov.parent_session_id) if prov else "none"

    def ev_type(ev: Any) -> str:
        raw_t = getattr(ev, "type", None) or (ev.get("type") if isinstance(ev, dict) else "")
        return str(raw_t).upper()

    thread_errors = [e for e in thread.events if ev_type(e) == "RUN_ERROR"]
    total_thread_errors = len(thread_errors)
    if total_thread_errors == 0 and (exc is not None or err_event.get("error_type")):
        total_thread_errors = 1

    failed_tools = [
        e
        for e in thread.events
        if ev_type(e) == "TOOL_CALL_RESULT"
        and (getattr(e, "is_error", None) or (e.get("is_error") if isinstance(e, dict) else False))
    ]

    payload = (
        f"Retry History & Execution Span:\n"
        f"- Session lineage depth: {lineage_depth}\n"
        f"- Prior parent session: {prior_session_id}\n"
        f"- Total errors in current thread: {total_thread_errors}\n"
        f"- Failed tool executions in span: {len(failed_tools)}\n\n"
        f"Failure Details:\n"
        f"- Error Type: {err_type}\n"
        f"- Error Message: {err_msg}\n"
        f"- Traceback:\n{formatted_tb}\n\n"
        f"Recent Conversation Messages:\n{history_text}"
    )
    return payload


async def execute_autocontinue(
    runner: SessionAgentRunner,
    thread: Thread,
    exc: Exception | None,
    err_event: dict[str, Any],
) -> Session | None:
    """Evaluate session failure with the autocontinue daemon and take action."""
    autocontinue_cfg = runner.session.config.daemons.autocontinue
    if not autocontinue_cfg.enabled or not autocontinue_cfg.model:
        return None

    provider = autocontinue_cfg.provider or runner.session.config.inference
    model = autocontinue_cfg.model

    input_payload = _format_autocontinue_payload(runner, thread, exc, err_event)
    active_key = _resolve_daemon_api_key(runner)

    steerable_id = daemon_instance_id(runner.session.id, daemon="autocontinue")
    raw_response = await invoke_daemon(
        provider=provider,
        model=model,
        instructions=AUTOCONTINUE_INSTRUCTIONS,
        input_payload=input_payload,
        api_key_override=active_key if autocontinue_cfg.provider is None else None,
        steerable_instance_id=steerable_id,
        raw=True,
    )

    should_retry = parse_autocontinue_response(raw_response)
    logger.info(
        "Autocontinue daemon decision for session %s: retry=%s (raw output: %r)",
        runner.session.id,
        should_retry,
        raw_response,
    )

    if not should_retry:
        return None

    bubble = find_last_successful_bubble(thread)
    if not bubble:
        logger.warning(
            "Autocontinue daemon wanted to retry session %s but found no successful bubble",
            runner.session.id,
        )
        return None

    target_id, item_type = bubble
    from seamus.harness.store import get_harness_store

    store = get_harness_store()
    try:
        branched = store.branch_session(
            agent_identifier=str(runner.session.agent_id),
            session_identifier=str(runner.session.id),
            target_id=target_id,
            position="after",
            item_type=item_type,
        )
        logger.info(
            "Autocontinue daemon branched session %s -> %s from bubble %s (%s)",
            runner.session.id,
            branched.id,
            target_id,
            item_type,
        )
        return branched
    except Exception:
        logger.exception(
            "Autocontinue daemon failed to branch session %s from bubble %s",
            runner.session.id,
            target_id,
        )
        return None
