import json
from typing import Any, Dict, List

from configs.settings import CONVERSATION_STYLE
from core.contracts import extract_json_object
from core.model_client import OllamaClient


class ConversationAgent:
    def __init__(self, model_client: OllamaClient | None = None):
        self.model_client = model_client or OllamaClient()

    def respond(
        self,
        message: str,
        memory: List[Dict[str, Any]] | None = None,
        run_state: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        memory = memory or []
        run_state = run_state or {}
        prompt = self._build_prompt(message, memory, run_state)
        model_response = self.model_client.generate_text(prompt)
        parsed = extract_json_object(model_response)

        if parsed:
            return self._normalize(parsed)

        return self._fallback_response(message, run_state)

    def narrate_step(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        action = entry.get("action", {})
        result = entry.get("result", {})
        review = entry.get("review", {})
        message = (
            f'I chose {action.get("action", "wait")} because '
            f'{action.get("reason", "it looked like the safest next step")} '
            f'The result was {result.get("status", "unknown")}. '
            f'{review.get("next_hint", "")}'
        ).strip()

        return {
            "intent": "status_update",
            "emotion": "focused",
            "response": message,
            "should_act": False,
            "goal": "",
        }

    def summarize_run(self, result: Dict[str, Any]) -> Dict[str, Any]:
        status = result.get("status", "unknown")
        steps = len(result.get("steps", []))
        tasks = result.get("tasks", [])
        completed_tasks = sum(1 for task in tasks if task.get("status") == "completed")
        total_tasks = len(tasks)
        feedback = result.get("final_feedback", "")

        if status == "done":
            response = (
                f"Done. I completed {completed_tasks}/{total_tasks} task(s) "
                f"in {steps} step(s). {feedback}"
            ).strip()
        elif status == "max_steps_reached":
            response = (
                f"I stopped after {steps} step(s), with {completed_tasks}/{total_tasks} "
                f"task(s) completed. I have not confirmed full completion yet. {feedback}"
            ).strip()
        elif status == "blocked":
            response = (
                f"I hit a blocker after {steps} step(s), with {completed_tasks}/{total_tasks} "
                f"task(s) completed. {feedback}"
            ).strip()
        else:
            response = f"I stopped with status {status}. {feedback}".strip()

        return {
            "intent": "run_summary",
            "emotion": "calm",
            "response": response,
            "should_act": False,
            "goal": "",
        }

    def _build_prompt(
        self,
        message: str,
        memory: List[Dict[str, Any]],
        run_state: Dict[str, Any],
    ) -> str:
        return f"""
You are the Conversation Agent for an autonomous IT engineering assistant.

Style:
{CONVERSATION_STYLE}

User message:
{message}

Recent memory:
{json.dumps(memory[-5:], indent=2, default=str)}

Current run state:
{json.dumps(run_state, indent=2, default=str)}

Rules:
- Sound natural and human, but do not claim to be human.
- Be concise, grounded, and technically useful.
- If the user asks the agent to do work, set should_act to true and convert it into a clear goal.
- If the user is just chatting or asking a question, set should_act to false.
- Return only valid JSON.

Response format:
{{
  "intent": "chat | question | command | status_update",
  "emotion": "calm | focused | friendly | cautious",
  "response": "natural spoken response",
  "should_act": true,
  "goal": "goal to run, or empty string"
}}
""".strip()

    def _normalize(self, response: Dict[str, Any]) -> Dict[str, Any]:
        intent = str(response.get("intent", "chat")).strip().lower()
        emotion = str(response.get("emotion", "friendly")).strip().lower()
        spoken = str(response.get("response", "")).strip()
        should_act = bool(response.get("should_act", False))
        goal = str(response.get("goal", "")).strip()

        if intent not in {"chat", "question", "command", "status_update", "run_summary"}:
            intent = "chat"
        if emotion not in {"calm", "focused", "friendly", "cautious"}:
            emotion = "friendly"
        if not spoken:
            spoken = "I am here. Tell me what you want me to look at or do next."

        return {
            "intent": intent,
            "emotion": emotion,
            "response": spoken,
            "should_act": should_act,
            "goal": goal,
        }

    def _fallback_response(
        self,
        message: str,
        run_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        lowered = message.lower()
        command_words = {"open", "click", "type", "search", "check", "fix", "run", "install"}
        should_act = any(word in lowered for word in command_words)
        goal = message.strip() if should_act else ""

        if run_state:
            response = "I am tracking the screen and memory. Tell me the next goal, and I will move carefully."
        elif should_act:
            response = f"Got it. I can work on this as a goal: {goal}"
        elif "hello" in lowered or "hi" in lowered:
            response = "Hey, I am here. What should we work on?"
        else:
            response = "I understand. Tell me what you want me to do next, and I will keep it careful and structured."

        return {
            "intent": "command" if should_act else "chat",
            "emotion": "friendly",
            "response": response,
            "should_act": should_act,
            "goal": goal,
        }
