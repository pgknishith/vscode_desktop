from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from configs.settings import AGENT_VERSION
from core.conversation import ConversationAgent
from core.contracts import normalize_action
from core.critic import Critic
from core.executor import Executor
from core.learning import LearningSystem
from core.memory import Memory
from core.model_client import OllamaClient
from core.planner import Planner
from core.safety import Safety
from core.tasks import TaskDecomposer
from core.voice import VoiceEngine
from perception.screen import analyze_screen, capture_screen


class Agent:
    def __init__(
        self,
        max_steps: int = 20,
        dry_run: bool | None = None,
        voice_enabled: bool | None = None,
    ):
        self.max_steps = max_steps
        self.model_client = OllamaClient()
        self.planner = Planner(self.model_client)
        self.executor = Executor() if dry_run is None else Executor(dry_run=dry_run)
        self.memory = Memory()
        self.safety = Safety()
        self.critic = Critic(self.model_client)
        self.decomposer = TaskDecomposer(self.model_client)
        self.learning = LearningSystem(self.model_client)
        self.conversation = ConversationAgent(self.model_client)
        self.voice = VoiceEngine() if voice_enabled is None else VoiceEngine(enabled=voice_enabled)

    def run(self, goal: str, speak: bool | None = None) -> Dict[str, Any]:
        critic_feedback = "No previous feedback"
        history: List[Dict[str, Any]] = []
        learning_context = self.learning.prepare(goal)
        tasks = self.decomposer.decompose(
            goal,
            self.memory.recent(),
            learning_context=learning_context,
        )
        run_id = str(uuid4())
        started_at = self._now()
        step = 0
        final_status = "done"

        for task in tasks:
            if step >= self.max_steps:
                final_status = "max_steps_reached"
                break

            task["status"] = "in_progress"

            while step < self.max_steps:
                screenshot_path = capture_screen()
                context = analyze_screen(screenshot_path)
                planner_memory = self.memory.recent() + history[-5:]

                action = self.planner.create_plan(
                    goal=goal,
                    context=context,
                    memory=planner_memory,
                    critic_feedback=critic_feedback,
                    failed_actions=self._failed_actions(history),
                    active_task=self._task_snapshot(task),
                    task_plan=[self._task_snapshot(item) for item in tasks],
                    learning_context=learning_context,
                )

                action = normalize_action(action)
                action_signature = self.memory.action_signature(action)
                safety = self.safety.check(action)

                previous_outcome = self.memory.action_outcome(action)
                if self._has_failed(action, history):
                    result = {
                        "status": "blocked",
                        "message": "Action was skipped because it already failed before.",
                        "previous_outcome": previous_outcome,
                    }
                elif not safety["allowed"]:
                    result = {
                        "status": safety["status"],
                        "message": safety["message"],
                    }
                else:
                    result = self.executor.execute(action)

                review = self.critic.evaluate(goal, action, result, context)
                critic_feedback = review.get("feedback", "")

                entry = {
                    "version": AGENT_VERSION,
                    "run_id": run_id,
                    "step": step,
                    "timestamp": self._now(),
                    "goal": goal,
                    "task": self._task_snapshot(task),
                    "agents": {
                        "decomposer": "TaskDecomposer",
                        "planner": "Planner",
                        "executor": "Executor",
                        "critic": "Critic",
                    },
                    "screen": context,
                    "action": action,
                    "action_signature": action_signature,
                    "previous_outcome": previous_outcome,
                    "safety": safety,
                    "result": result,
                    "review": review,
                }
                self.memory.store(entry)
                history.append(entry)
                task["steps"].append(
                    {
                        "step": step,
                        "action": action,
                        "result": result,
                        "review": review,
                    }
                )
                step += 1

                if action["action"] == "done":
                    task["result"] = action.get("reason", "Task marked complete.")
                    if self._done_action_is_blocked(action):
                        task["status"] = "blocked"
                        final_status = "blocked"
                        critic_feedback = task["result"]
                    else:
                        task["status"] = "completed"
                    break

                if result.get("status") in {"blocked", "unsafe"}:
                    task["status"] = "blocked"
                    task["result"] = result.get("message", "Task blocked.")
                    final_status = "blocked"
                    break

            if task["status"] == "in_progress":
                task["status"] = "blocked"
                task["result"] = "Step budget ended before this task completed."
                final_status = "max_steps_reached"
                break

            if task["status"] == "blocked":
                break

        final_result = self._finish(
            final_status,
            goal,
            run_id,
            started_at,
            history,
            critic_feedback,
            tasks=tasks,
            learning_context=learning_context,
            speak=speak,
        )
        final_result["learning"]["expertise_update"] = self.learning.record_goal(goal, final_result)
        return final_result

    def chat(
        self,
        message: str,
        speak: bool | None = None,
        auto_run: bool = False,
    ) -> Dict[str, Any]:
        response = self.conversation.respond(message=message, memory=self.memory.recent())
        speech = self._speak(response["response"], speak)
        payload: Dict[str, Any] = {
            "version": AGENT_VERSION,
            "mode": "conversation",
            "message": message,
            "conversation": response,
            "speech": speech,
            "model_enabled": self.model_client.enabled,
            "learning": self.learning.status(),
        }

        if auto_run and response.get("should_act") and response.get("goal"):
            payload["run"] = self.run(response["goal"], speak=speak)

        return payload

    def learn(
        self,
        topic: str,
        sources: List[str] | None = None,
        speak: bool | None = None,
    ) -> Dict[str, Any]:
        result = self.learning.learn_topic(topic, sources or [])
        entries = len(result.get("entries", []))
        response = {
            "intent": "learning_update",
            "emotion": "focused",
            "response": f"I learned {entries} source(s) for {topic}.",
            "should_act": False,
            "goal": "",
        }
        return {
            "version": AGENT_VERSION,
            "mode": "learning",
            "topic": topic,
            "learning": result,
            "conversation": response,
            "speech": self._speak(response["response"], speak),
        }

    def learning_status(self) -> Dict[str, Any]:
        return {
            "version": AGENT_VERSION,
            "mode": "learning_status",
            "learning": self.learning.status(),
        }

    def voices(self) -> Dict[str, Any]:
        return self.voice.available_voices()

    def _finish(
        self,
        status: str,
        goal: str,
        run_id: str,
        started_at: str,
        history: List[Dict[str, Any]],
        critic_feedback: str,
        tasks: List[Dict[str, Any]] | None = None,
        learning_context: Dict[str, Any] | None = None,
        speak: bool | None = None,
    ) -> Dict[str, Any]:
        tasks = tasks or []
        learning_context = learning_context or {}
        summary = self.conversation.summarize_run(
            {
                "status": status,
                "goal": goal,
                "tasks": tasks,
                "steps": history,
                "final_feedback": critic_feedback,
            }
        )
        speech = self._speak(summary["response"], speak)

        return {
            "version": AGENT_VERSION,
            "status": status,
            "goal": goal,
            "run_id": run_id,
            "started_at": started_at,
            "ended_at": self._now(),
            "model_enabled": self.model_client.enabled,
            "memory": self.memory.stats(),
            "tasks": tasks,
            "learning": learning_context,
            "conversation": summary,
            "speech": speech,
            "steps": history,
            "final_feedback": critic_feedback,
        }

    def _task_snapshot(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": task.get("id", ""),
            "title": task.get("title", ""),
            "objective": task.get("objective", ""),
            "success_criteria": task.get("success_criteria", ""),
            "risk": task.get("risk", ""),
            "status": task.get("status", ""),
            "result": task.get("result", ""),
        }

    def _done_action_is_blocked(self, action: Dict[str, str]) -> bool:
        reason = action.get("reason", "").lower()
        blocked_phrases = {
            "blocker",
            "no log path",
            "no visible log context",
            "no specific low-risk remediation",
            "no system change is applied",
        }
        return any(phrase in reason for phrase in blocked_phrases)

    def _failed_actions(self, history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        failed = self.memory.failed_actions()
        for entry in history:
            if entry.get("result", {}).get("status") not in {"fail", "blocked", "unsafe"}:
                continue
            action = entry.get("action", {})
            failed.append(
                {
                    "action": action.get("action", ""),
                    "target": action.get("target", ""),
                    "text": action.get("text", ""),
                    "command": action.get("command", ""),
                    "reason": action.get("reason", ""),
                }
            )
        return failed

    def _has_failed(self, action: Dict[str, str], history: List[Dict[str, Any]]) -> bool:
        signature = self.memory.action_signature(action)
        if self.memory.has_failed(action):
            return True

        return any(
            entry.get("action_signature") == signature
            and entry.get("result", {}).get("status") in {"fail", "blocked", "unsafe"}
            for entry in history
        )

    def _speak(self, text: str, speak: bool | None) -> Dict[str, Any]:
        if speak is None:
            return self.voice.speak(text)

        previous = self.voice.enabled
        self.voice.enabled = speak
        try:
            return self.voice.speak(text)
        finally:
            self.voice.enabled = previous

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
