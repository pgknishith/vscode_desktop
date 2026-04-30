import json
from typing import Any, Dict

from core.contracts import normalize_review
from core.model_client import OllamaClient


class Critic:
    def __init__(self, model_client: OllamaClient | None = None):
        self.model_client = model_client or OllamaClient()

    def evaluate(
        self,
        goal: str,
        action: Dict[str, str],
        result: Dict[str, str],
        context: Dict[str, Any],
    ) -> Dict[str, str]:
        prompt = self._build_prompt(goal, action, result, context)
        response = self.model_client.generate_json(prompt)

        if response:
            return normalize_review(response)

        return normalize_review(self._fallback_review(action, result))

    def _build_prompt(
        self,
        goal: str,
        action: Dict[str, str],
        result: Dict[str, str],
        context: Dict[str, Any],
    ) -> str:
        return f"""
You are the Critic Agent in an autonomous IT engineering loop.

Goal:
{goal}

Action taken:
{json.dumps(action, indent=2)}

Result:
{json.dumps(result, indent=2)}

Screen:
{json.dumps(context, indent=2)}

Evaluate:
- Was the action safe?
- Did it help progress the goal?
- What should be improved?

Return only valid JSON:
{{
  "status": "success | fail | improve",
  "feedback": "...",
  "next_hint": "..."
}}
""".strip()

    def _fallback_review(
        self,
        action: Dict[str, str],
        result: Dict[str, str],
    ) -> Dict[str, str]:
        status = result.get("status", "fail")

        if action.get("action") == "done" and status == "success":
            return {
                "status": "success",
                "feedback": "Goal was marked complete.",
                "next_hint": "Stop execution.",
            }

        if status == "success":
            return {
                "status": "success",
                "feedback": "Action executed successfully; continue toward the goal.",
                "next_hint": "Observe the next screen before planning another step.",
            }

        return {
            "status": "fail",
            "feedback": result.get("message", "Action failed."),
            "next_hint": "Choose a different safe action and do not repeat this one.",
        }
