import json
from typing import Any, Dict, List

from core.contracts import action_signature, normalize_action
from core.model_client import OllamaClient


class Planner:
    def __init__(self, model_client: OllamaClient | None = None):
        self.model_client = model_client or OllamaClient()

    def create_plan(
        self,
        goal: str,
        context: Dict[str, Any],
        memory: List[Dict[str, Any]],
        critic_feedback: str,
        failed_actions: List[Dict[str, str]],
        active_task: Dict[str, Any] | None = None,
        task_plan: List[Dict[str, Any]] | None = None,
        learning_context: Dict[str, Any] | None = None,
    ) -> Dict[str, str]:
        prompt = self._build_prompt(
            goal,
            context,
            memory,
            critic_feedback,
            failed_actions,
            active_task,
            task_plan or [],
            learning_context or {},
        )
        response = self.model_client.generate_json(prompt)

        if response:
            return normalize_action(response)

        return normalize_action(
            self._fallback_plan(
                goal,
                context,
                memory,
                failed_actions,
                critic_feedback,
                active_task,
            )
        )

    def _build_prompt(
        self,
        goal: str,
        context: Dict[str, Any],
        memory: List[Dict[str, Any]],
        critic_feedback: str,
        failed_actions: List[Dict[str, str]],
        active_task: Dict[str, Any] | None,
        task_plan: List[Dict[str, Any]],
        learning_context: Dict[str, Any],
    ) -> str:
        return f"""
You are the Planner Agent in an autonomous IT engineering loop.

Parent goal:
{goal}

Active task:
{json.dumps(active_task or {}, indent=2)}

Full task plan:
{json.dumps(task_plan, indent=2)}

Learning context:
{json.dumps(learning_context, indent=2, default=str)}

Screen context:
{json.dumps(context, indent=2)}

Recent memory:
{json.dumps(memory, indent=2)}

Known failed actions:
{json.dumps(failed_actions, indent=2)}

Critic feedback:
{critic_feedback}

Rules:
- Return only valid JSON.
- Never repeat an action listed in Known failed actions.
- Prefer safe, reversible actions.
- Break goals into small steps.
- If the active task is complete, return done.
- Use only these actions: click_text, type, wait, run_command, done.
- Do not invent screen text. click_text targets must appear in Screen context.
- run_command is for allowlisted read-only diagnostics only.

Action format:
{{
  "action": "click_text | type | wait | run_command | done",
  "target": "text on screen",
  "text": "optional input",
  "command": "optional safe diagnostic command",
  "reason": "why this step"
}}
""".strip()

    def _fallback_plan(
        self,
        goal: str,
        context: Dict[str, Any],
        memory: List[Dict[str, Any]],
        failed_actions: List[Dict[str, str]],
        critic_feedback: str,
        active_task: Dict[str, Any] | None,
    ) -> Dict[str, str]:
        visible_text = " ".join(context.get("text", []))
        failed_signatures = {
            action_signature(item) for item in failed_actions
        }
        successful_signatures = {
            entry.get("action_signature", "")
            for entry in memory
            if active_task
            and entry.get("task", {}).get("id") == active_task.get("id")
            and entry.get("result", {}).get("status") == "success"
        }
        task_text = " ".join(
            [
                str((active_task or {}).get("title", "")),
                str((active_task or {}).get("objective", "")),
                str((active_task or {}).get("success_criteria", "")),
            ]
        ).lower()

        if active_task and "gather symptoms" in task_text:
            return {
                "action": "done",
                "target": "",
                "text": "",
                "command": "",
                "reason": "No specific server target is visible yet; continuing with safe diagnostics.",
            }

        if active_task and "safe diagnostics" in task_text:
            for command in ("ipconfig", "netstat -ano", "tasklist"):
                candidate = {
                    "action": "run_command",
                    "target": "",
                    "text": command,
                    "command": command,
                    "reason": "Collect read-only server and network diagnostic context.",
                }
                signature = action_signature(candidate)
                if signature not in failed_signatures and signature not in successful_signatures:
                    return candidate

            return {
                "action": "done",
                "target": "",
                "text": "",
                "command": "",
                "reason": "All fallback read-only diagnostics have already been captured.",
            }

        if active_task and "logs" in task_text:
            return {
                "action": "done",
                "target": "",
                "text": "",
                "command": "",
                "reason": "No log path or visible log context is available; this blocker is recorded.",
            }

        if active_task and "remediation" in task_text:
            return {
                "action": "done",
                "target": "",
                "text": "",
                "command": "",
                "reason": "No specific low-risk remediation is proven yet, so no system change is applied.",
            }

        if active_task and "verify" in task_text:
            candidate = {
                "action": "run_command",
                "target": "",
                "text": "netstat -ano",
                "command": "netstat -ano",
                "reason": "Re-check listening ports as a safe verification signal.",
            }
            if action_signature(candidate) not in failed_signatures:
                if action_signature(candidate) not in successful_signatures:
                    return candidate
                return {
                    "action": "done",
                    "target": "",
                    "text": "",
                    "command": "",
                    "reason": "Verification diagnostic has been captured.",
                }

        if active_task and self._task_has_successful_non_wait(memory, active_task):
            return {
                "action": "done",
                "target": "",
                "text": "",
                "command": "",
                "reason": "The active task has a successful concrete step recorded.",
            }

        if "browser" in goal.lower() and "browser" in visible_text.lower():
            candidate = {
                "action": "click_text",
                "target": "browser",
                "text": "",
                "command": "",
                "reason": "The goal mentions opening a browser and browser text is visible.",
            }
            if action_signature(candidate) not in failed_signatures:
                return candidate

        if "search" in goal.lower() and context.get("text"):
            candidate = {
                "action": "type",
                "target": "",
                "text": goal,
                "command": "",
                "reason": "Type the goal into the currently focused UI as a safe next step.",
            }
            if action_signature(candidate) not in failed_signatures:
                return candidate

        feedback = critic_feedback.lower()
        if "goal was marked complete" in feedback or "goal is complete" in feedback:
            return {
                "action": "done",
                "target": "",
                "text": "",
                "command": "",
                "reason": "The critic indicates the goal is complete.",
            }

        return {
            "action": "wait",
            "target": "",
            "text": "",
            "command": "",
            "reason": "No safe target is available from the current screen context.",
        }

    def _task_has_successful_non_wait(
        self,
        memory: List[Dict[str, Any]],
        active_task: Dict[str, Any],
    ) -> bool:
        task_id = active_task.get("id")
        for entry in reversed(memory):
            if entry.get("task", {}).get("id") != task_id:
                continue
            action_name = entry.get("action", {}).get("action")
            if action_name not in {"wait", "done"} and entry.get("result", {}).get("status") == "success":
                return True
        return False
