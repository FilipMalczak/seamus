"""Daemon subpackage for one-shot background LLM utilities."""

from seamus.harness.daemons.autocontinue import (
    AutocontinueAction,
    execute_autocontinue,
    find_last_successful_bubble,
    parse_autocontinue_response,
)
from seamus.harness.daemons.engine import invoke_daemon
from seamus.harness.daemons.formatter import format_thread_history
from seamus.harness.daemons.naming import (
    execute_session_naming,
    execute_thread_naming,
    is_stepback_trigger,
)
from seamus.harness.daemons.parser import parse_loose_slug

__all__ = [
    "AutocontinueAction",
    "execute_autocontinue",
    "execute_session_naming",
    "execute_thread_naming",
    "find_last_successful_bubble",
    "format_thread_history",
    "invoke_daemon",
    "is_stepback_trigger",
    "parse_autocontinue_response",
    "parse_loose_slug",
]
