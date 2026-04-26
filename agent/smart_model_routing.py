"""Helpers for optional cheap-vs-strong model routing."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

from utils import is_truthy_value

_COMPLEX_KEYWORDS = {
    "debug",
    "debugging",
    "implement",
    "implementation",
    "refactor",
    "patch",
    "traceback",
    "stacktrace",
    "exception",
    "error",
    "analyze",
    "analysis",
    "investigate",
    "architecture",
    "design",
    "compare",
    "benchmark",
    "optimize",
    "optimise",
    "review",
    "terminal",
    "shell",
    "tool",
    "tools",
    "pytest",
    "test",
    "tests",
    "plan",
    "planning",
    "delegate",
    "subagent",
    "cron",
    "docker",
    "kubernetes",
}

_PRIMARY_ONLY_COMPLEX_KEYWORDS = {
    "debug",
    "debugging",
    "implement",
    "implementation",
    "refactor",
    "patch",
    "traceback",
    "stacktrace",
    "exception",
    "error",
    "analyze",
    "analysis",
    "investigate",
    "architecture",
    "design",
    "compare",
    "benchmark",
    "optimize",
    "optimise",
    "review",
    "plan",
    "planning",
}

_TOOL_PHASE_KEYWORDS = {
    "tool",
    "tools",
    "terminal",
    "shell",
    "browser",
    "web",
    "search",
    "find",
    "read",
    "open",
    "check",
    "pytest",
    "test",
    "tests",
    "delegate",
    "subagent",
    "cron",
    "docker",
    "kubernetes",
    "git",
    "repo",
    "logs",
    "log",
}

_EXPLICIT_TASK_PREFIXES = (
    "please ",
    "can you ",
    "could you ",
    "would you ",
    "will you ",
    "i need you to ",
    "i want you to ",
    "help me ",
    "go ",
    "run ",
    "check ",
    "look ",
    "open ",
    "search ",
    "find ",
    "read ",
    "write ",
    "draft ",
    "send ",
    "create ",
    "make ",
    "add ",
    "update ",
    "change ",
    "edit ",
    "fix ",
    "install ",
    "deploy ",
    "sync ",
)

_EXPLICIT_TASK_PHRASES = (
    " for me",
    " look into",
    " take a look",
    " go and ",
)

_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    return is_truthy_value(value, default=default)


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _looks_like_explicit_task(text: str, words: set[str]) -> bool:
    lowered = text.lower().strip()
    if any(lowered.startswith(prefix) for prefix in _EXPLICIT_TASK_PREFIXES):
        return True
    if any(phrase in lowered for phrase in _EXPLICIT_TASK_PHRASES):
        return True
    if lowered.endswith("?") and bool(words & _TOOL_PHASE_KEYWORDS):
        return True
    return False


def _looks_tool_heavy(words: set[str]) -> bool:
    return bool(words & _TOOL_PHASE_KEYWORDS)


def choose_cheap_model_route(user_message: str, routing_config: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the configured cheap-model route when a message looks simple.

    Conservative by design: if the message has signs of code/tool/debugging/
    long-form work, keep the primary model.
    """
    cfg = routing_config or {}
    if not _coerce_bool(cfg.get("enabled"), False):
        return None

    cheap_model = cfg.get("cheap_model") or {}
    if not isinstance(cheap_model, dict):
        return None
    provider = str(cheap_model.get("provider") or "").strip().lower()
    model = str(cheap_model.get("model") or "").strip()
    if not provider or not model:
        return None

    text = (user_message or "").strip()
    if not text:
        return None

    max_chars = _coerce_int(cfg.get("max_simple_chars"), 160)
    max_words = _coerce_int(cfg.get("max_simple_words"), 28)

    if len(text) > max_chars:
        return None
    if len(text.split()) > max_words:
        return None
    if text.count("\n") > 1:
        return None
    if "```" in text or "`" in text:
        return None
    if _URL_RE.search(text):
        return None

    lowered = text.lower()
    words = {token.strip(".,:;!?()[]{}\"'`") for token in lowered.split()}
    if words & _PRIMARY_ONLY_COMPLEX_KEYWORDS:
        return None

    explicit_task = _looks_like_explicit_task(text, words)
    if explicit_task:
        if not _looks_tool_heavy(words):
            return None
        route = dict(cheap_model)
        route["provider"] = provider
        route["model"] = model
        route["routing_reason"] = "tool_phase_only"
        route["restore_primary_after_tool_selection"] = True
        return route

    if words & _COMPLEX_KEYWORDS:
        return None

    route = dict(cheap_model)
    route["provider"] = provider
    route["model"] = model
    route["routing_reason"] = "simple_turn"
    route["restore_primary_after_tool_selection"] = False
    return route


def resolve_turn_route(user_message: str, routing_config: Optional[Dict[str, Any]], primary: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve the effective model/runtime for one turn.

    Returns a dict with model/runtime/signature/label fields.
    """
    primary_runtime = {
        "api_key": primary.get("api_key"),
        "base_url": primary.get("base_url"),
        "provider": primary.get("provider"),
        "api_mode": primary.get("api_mode"),
        "command": primary.get("command"),
        "args": list(primary.get("args") or []),
        "credential_pool": primary.get("credential_pool"),
    }

    route = choose_cheap_model_route(user_message, routing_config)
    if not route:
        return {
            "model": primary.get("model"),
            "runtime": dict(primary_runtime),
            "primary_model": primary.get("model"),
            "primary_runtime": dict(primary_runtime),
            "restore_primary_after_tool_selection": False,
            "label": None,
            "signature": (
                primary.get("model"),
                primary.get("provider"),
                primary.get("base_url"),
                primary.get("api_mode"),
                primary.get("command"),
                tuple(primary.get("args") or ()),
            ),
        }

    from hermes_cli.runtime_provider import resolve_runtime_provider

    explicit_api_key = None
    api_key_env = str(route.get("api_key_env") or "").strip()
    if api_key_env:
        explicit_api_key = os.getenv(api_key_env) or None

    try:
        runtime = resolve_runtime_provider(
            requested=route.get("provider"),
            explicit_api_key=explicit_api_key,
            explicit_base_url=route.get("base_url"),
        )
    except Exception:
        return {
            "model": primary.get("model"),
            "runtime": dict(primary_runtime),
            "primary_model": primary.get("model"),
            "primary_runtime": dict(primary_runtime),
            "restore_primary_after_tool_selection": False,
            "label": None,
            "signature": (
                primary.get("model"),
                primary.get("provider"),
                primary.get("base_url"),
                primary.get("api_mode"),
                primary.get("command"),
                tuple(primary.get("args") or ()),
            ),
        }

    return {
        "model": route.get("model"),
        "runtime": {
            "api_key": runtime.get("api_key"),
            "base_url": runtime.get("base_url"),
            "provider": runtime.get("provider"),
            "api_mode": runtime.get("api_mode"),
            "command": runtime.get("command"),
            "args": list(runtime.get("args") or []),
            "credential_pool": runtime.get("credential_pool"),
        },
        "primary_model": primary.get("model"),
        "primary_runtime": dict(primary_runtime),
        "restore_primary_after_tool_selection": bool(route.get("restore_primary_after_tool_selection")),
        "label": f"smart route → {route.get('model')} ({runtime.get('provider')})",
        "signature": (
            route.get("model"),
            runtime.get("provider"),
            runtime.get("base_url"),
            runtime.get("api_mode"),
            runtime.get("command"),
            tuple(runtime.get("args") or ()),
        ),
    }
