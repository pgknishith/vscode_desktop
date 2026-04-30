import json
from typing import Any, Dict, List

from core.contracts import extract_json_object
from core.model_client import OllamaClient


TASK_STATUSES = {"pending", "in_progress", "completed", "blocked"}


class TaskDecomposer:
    def __init__(self, model_client: OllamaClient | None = None):
        self.model_client = model_client or OllamaClient()

    def decompose(
        self,
        goal: str,
        memory: List[Dict[str, Any]] | None = None,
        learning_context: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        memory = memory or []
        learning_context = learning_context or {}
        prompt = self._build_prompt(goal, memory, learning_context)
        response = self.model_client.generate_text(prompt)
        parsed = extract_json_object(response)

        if parsed and isinstance(parsed.get("tasks"), list):
            tasks = [normalize_task(task, index) for index, task in enumerate(parsed["tasks"], 1)]
            if tasks:
                return tasks

        return self._fallback_tasks(goal)

    def _build_prompt(
        self,
        goal: str,
        memory: List[Dict[str, Any]],
        learning_context: Dict[str, Any],
    ) -> str:
        return f"""
You are the Task Decomposer for an autonomous AI IT engineer.

Goal:
{goal}

Recent memory:
{json.dumps(memory[-5:], indent=2, default=str)}

Learning context:
{json.dumps(learning_context, indent=2, default=str)}

Break the goal into practical, ordered sub-tasks. Each sub-task must be small enough
for a planner/executor/critic loop to attempt safely.

Rules:
- Return only valid JSON.
- Prefer diagnosis before remediation.
- Include verification as the final task.
- Do not include destructive remediation unless the task says it must be confirmed first.
- If the goal is vague, start with gathering symptoms and environment context.
- Use the learning path and knowledge context to choose better sub-tasks.

Response format:
{{
  "tasks": [
    {{
      "id": "task-1",
      "title": "Short task name",
      "objective": "Concrete objective",
      "success_criteria": "How the agent knows this sub-task is complete",
      "risk": "low | medium | high",
      "status": "pending"
    }}
  ]
}}
""".strip()

    def _fallback_tasks(self, goal: str) -> List[Dict[str, Any]]:
        lowered = goal.lower()

        if "server" in lowered or "service" in lowered or "issue" in lowered:
            return [
                normalize_task(
                    {
                        "title": "Gather symptoms",
                        "objective": "Identify the affected server, service, visible errors, and recent context from screen or memory.",
                        "success_criteria": "Known symptoms and target context are captured, or missing details are documented.",
                        "risk": "low",
                    },
                    1,
                ),
                normalize_task(
                    {
                        "title": "Collect safe diagnostics",
                        "objective": "Collect safe local diagnostics for network configuration, listening ports, and active processes.",
                        "success_criteria": "Read-only diagnostic output is captured without changing the system.",
                        "risk": "low",
                    },
                    2,
                ),
                normalize_task(
                    {
                        "title": "Inspect logs and errors",
                        "objective": "Look for visible log files, error messages, or service output related to the issue.",
                        "success_criteria": "A likely error source is found or the absence of log context is recorded.",
                        "risk": "low",
                    },
                    3,
                ),
                normalize_task(
                    {
                        "title": "Apply safe remediation",
                        "objective": "Apply only reversible, low-risk remediation when the cause is clear; otherwise stop and report the blocker.",
                        "success_criteria": "A safe fix is applied, or the exact missing detail is reported.",
                        "risk": "medium",
                    },
                    4,
                ),
                normalize_task(
                    {
                        "title": "Verify recovery",
                        "objective": "Re-check health indicators and confirm whether the server issue is resolved.",
                        "success_criteria": "The server appears healthy, or remaining failure evidence is summarized.",
                        "risk": "low",
                    },
                    5,
                ),
            ]

        return [
            normalize_task(
                {
                    "title": "Understand goal",
                    "objective": f"Clarify and ground the goal: {goal}",
                    "success_criteria": "The goal has enough context to act safely.",
                    "risk": "low",
                },
                1,
            ),
            normalize_task(
                {
                    "title": "Execute safe next step",
                    "objective": f"Perform the safest reversible action toward: {goal}",
                    "success_criteria": "A safe action is completed or a blocker is reported.",
                    "risk": "low",
                },
                2,
            ),
            normalize_task(
                {
                    "title": "Verify outcome",
                    "objective": f"Verify whether the goal was achieved: {goal}",
                    "success_criteria": "The result is verified or remaining work is summarized.",
                    "risk": "low",
                },
                3,
            ),
        ]


def normalize_task(task: Dict[str, Any], index: int) -> Dict[str, Any]:
    status = str(task.get("status", "pending")).strip().lower()
    if status not in TASK_STATUSES:
        status = "pending"

    return {
        "id": str(task.get("id") or f"task-{index}"),
        "title": str(task.get("title") or f"Task {index}").strip(),
        "objective": str(task.get("objective") or "").strip(),
        "success_criteria": str(task.get("success_criteria") or "").strip(),
        "risk": str(task.get("risk", "low")).strip().lower(),
        "status": status,
        "steps": [],
        "result": "",
    }
