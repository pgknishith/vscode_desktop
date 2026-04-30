from typing import Dict

from configs.settings import ALLOWED_COMMAND_PREFIXES, COMMANDS_ENABLED
from core.contracts import ALLOWED_ACTIONS


class Safety:
    ALLOWED_ACTIONS = ALLOWED_ACTIONS
    BLOCKED_TERMS = {
        "delete",
        "format",
        "shutdown",
        "restart",
        "regedit",
        "rm -rf",
        "wipe",
        "credential",
        "password",
        "secret",
        "token",
        "apikey",
    }
    SHELL_CONTROL_TOKENS = {"&", "|", ";", ">", "<", "`", "$("}

    def validate(self, action: Dict[str, str]) -> bool:
        return self.check(action)["allowed"]

    def check(self, action: Dict[str, str]) -> Dict[str, object]:
        if action.get("action") not in self.ALLOWED_ACTIONS:
            return {
                "allowed": False,
                "status": "unsafe",
                "message": f'Unsupported action: {action.get("action")}',
            }

        if action.get("action") == "click_text" and not action.get("target"):
            return {
                "allowed": False,
                "status": "unsafe",
                "message": "click_text requires visible target text.",
            }

        if action.get("action") == "type" and not action.get("text"):
            return {
                "allowed": False,
                "status": "unsafe",
                "message": "type requires text.",
            }

        if action.get("action") == "run_command":
            command_check = self._check_command(action.get("command") or action.get("text", ""))
            if not command_check["allowed"]:
                return command_check

        action_text = str(action).lower()
        blocked_term = next(
            (term for term in self.BLOCKED_TERMS if term in action_text),
            "",
        )
        if blocked_term:
            return {
                "allowed": False,
                "status": "unsafe",
                "message": f"Blocked unsafe term: {blocked_term}",
            }

        return {
            "allowed": True,
            "status": "safe",
            "message": "Action passed safety checks.",
        }

    def _check_command(self, command: str) -> Dict[str, object]:
        command = command.strip()
        lowered = command.lower()

        if not COMMANDS_ENABLED:
            return {
                "allowed": False,
                "status": "unsafe",
                "message": "System command execution is disabled.",
            }

        if not command:
            return {
                "allowed": False,
                "status": "unsafe",
                "message": "run_command requires a command.",
            }

        control_token = next(
            (token for token in self.SHELL_CONTROL_TOKENS if token in command),
            "",
        )
        if control_token:
            return {
                "allowed": False,
                "status": "unsafe",
                "message": f"Blocked shell control token: {control_token}",
            }

        if not any(lowered.startswith(prefix) for prefix in ALLOWED_COMMAND_PREFIXES):
            return {
                "allowed": False,
                "status": "unsafe",
                "message": f"Command prefix is not allowlisted: {command}",
            }

        return {
            "allowed": True,
            "status": "safe",
            "message": "Read-only command passed safety checks.",
        }
