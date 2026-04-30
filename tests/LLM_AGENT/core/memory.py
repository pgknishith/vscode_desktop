import json
from pathlib import Path
from typing import Any, Dict, List

from configs.settings import MEMORY_PATH
from core.contracts import action_signature


class Memory:
    def __init__(self, file_path: str | Path = MEMORY_PATH):
        self.file = Path(file_path)
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.data = self.load()

    def load(self) -> List[Dict[str, Any]]:
        if not self.file.exists():
            return []

        try:
            with self.file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def store(self, entry: Dict[str, Any]) -> None:
        self.data.append(entry)
        with self.file.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2, default=str)

    def recent(self, n: int = 5) -> List[Dict[str, Any]]:
        return self.data[-n:]

    def failed_actions(self, limit: int | None = None) -> List[Dict[str, str]]:
        failed = []
        entries = self.data[-limit:] if limit else self.data
        for entry in entries:
            result = entry.get("result", {})
            if result.get("status") in {"fail", "blocked", "unsafe"}:
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

    def has_failed(self, action: Dict[str, str]) -> bool:
        signature = self.action_signature(action)
        return any(
            entry.get("action_signature") == signature
            and entry.get("result", {}).get("status") in {"fail", "blocked", "unsafe"}
            for entry in self.data
        )

    def action_outcome(self, action: Dict[str, str]) -> Dict[str, str]:
        signature = self.action_signature(action)
        for entry in reversed(self.data):
            if entry.get("action_signature") != signature:
                continue
            result = entry.get("result", {})
            return {
                "status": str(result.get("status", "unknown")),
                "message": str(result.get("message", "")),
                "step": str(entry.get("step", "")),
                "goal": str(entry.get("goal", "")),
            }

        return {
            "status": "new",
            "message": "Action has not been attempted before.",
            "step": "",
            "goal": "",
        }

    def action_signature(self, action: Dict[str, str]) -> str:
        return action_signature(action)

    def stats(self) -> Dict[str, int]:
        total = len(self.data)
        failed = sum(
            1
            for entry in self.data
            if entry.get("result", {}).get("status") in {"fail", "blocked", "unsafe"}
        )
        return {
            "total_steps": total,
            "failed_steps": failed,
            "successful_steps": total - failed,
        }
