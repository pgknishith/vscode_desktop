import json
from typing import Any, Dict, Optional


ALLOWED_ACTIONS = {"click_text", "type", "wait", "run_command", "done"}


def normalize_action(action: Any) -> Dict[str, str]:
    if isinstance(action, str):
        parsed = extract_json_object(action)
        action = parsed if parsed is not None else {}

    if not isinstance(action, dict):
        action = {}

    normalized = {
        "action": str(action.get("action", "wait")).strip().lower(),
        "target": str(action.get("target", "")).strip(),
        "text": str(action.get("text", "")).strip(),
        "command": str(action.get("command", "")).strip(),
        "reason": str(action.get("reason", "No reason provided.")).strip(),
    }

    if normalized["action"] == "run_command" and not normalized["command"]:
        normalized["command"] = normalized["text"]

    if normalized["action"] not in ALLOWED_ACTIONS:
        normalized["action"] = "wait"
        normalized["target"] = ""
        normalized["text"] = ""
        normalized["command"] = ""
        normalized["reason"] = "Planner returned an unsupported action."

    return normalized


def normalize_review(review: Any) -> Dict[str, str]:
    if isinstance(review, str):
        parsed = extract_json_object(review)
        review = parsed if parsed is not None else {}

    if not isinstance(review, dict):
        review = {}

    status = str(review.get("status", "improve")).strip().lower()
    if status not in {"success", "fail", "improve"}:
        status = "improve"

    return {
        "status": status,
        "feedback": str(review.get("feedback", "")).strip(),
        "next_hint": str(review.get("next_hint", "")).strip(),
    }


def action_signature(action: Dict[str, str]) -> str:
    if action.get("action") == "done":
        return f'done::::{action.get("reason", "")}'

    command = action.get("command") or action.get("text", "")
    return f'{action.get("action", "")}::{action.get("target", "")}::{action.get("text", "")}::{command}'


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    if not text:
        return None

    for candidate in (text, _balanced_json_slice(text)):
        if not candidate:
            continue
        try:
            value = json.loads(_strip_code_fence(candidate))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value

    return None


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```") or not stripped.endswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) <= 2:
        return stripped
    return "\n".join(lines[1:-1]).strip()


def _balanced_json_slice(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return ""

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(text)):
        char = text[index]

        if escape:
            escape = False
            continue

        if char == "\\":
            escape = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return ""
