import subprocess
import time
from typing import Any, Dict

try:
    import pyautogui
except ImportError:
    pyautogui = None

from configs.settings import ACTION_DELAY_SECONDS, COMMAND_TIMEOUT_SECONDS, DRY_RUN
from perception.vision import locate_text


class Executor:
    def __init__(self, dry_run: bool = DRY_RUN):
        self.dry_run = dry_run

    def execute(self, action: Dict[str, str]) -> Dict[str, Any]:
        act = action.get("action", "wait")

        if act == "click_text":
            return self._click_text(action.get("target", ""))

        if act == "type":
            return self._type(action.get("text", ""))

        if act == "wait":
            time.sleep(ACTION_DELAY_SECONDS)
            return {"status": "success", "message": "Waited for screen state to change."}

        if act == "run_command":
            return self._run_command(action.get("command") or action.get("text", ""))

        if act == "done":
            return {"status": "success", "message": "Goal marked complete."}

        return {"status": "fail", "message": f"Unknown action: {act}"}

    def _click_text(self, target: str) -> Dict[str, Any]:
        if not target:
            return {"status": "fail", "message": "click_text requires a target."}

        if self.dry_run:
            return {
                "status": "success",
                "message": f"Dry run: would click text target: {target}",
            }

        if pyautogui is None:
            return {"status": "fail", "message": "pyautogui is not installed."}

        match = locate_text(target)
        if not match:
            return {"status": "fail", "message": f"Text target was not found: {target}"}

        center = match["center"]
        position = (int(center["x"]), int(center["y"]))

        try:
            pyautogui.moveTo(*position, duration=0.05)
            pyautogui.click(*position)
        except Exception as error:
            return {"status": "fail", "message": f"Click failed: {error}"}

        return {
            "status": "success",
            "message": f"Clicked text target: {target}",
            "x": str(position[0]),
            "y": str(position[1]),
            "matched_text": str(match.get("text", "")),
            "match_score": str(match.get("score", "")),
            "match_confidence": str(match.get("confidence", "")),
        }

    def _type(self, text: str) -> Dict[str, Any]:
        if not text:
            return {"status": "fail", "message": "type requires text."}

        if self.dry_run:
            return {"status": "success", "message": "Dry run: would type requested text."}

        if pyautogui is None:
            return {"status": "fail", "message": "pyautogui is not installed."}

        try:
            pyautogui.write(text)
        except Exception as error:
            return {"status": "fail", "message": f"Typing failed: {error}"}

        return {"status": "success", "message": "Typed requested text."}

    def _run_command(self, command: str) -> Dict[str, Any]:
        if not command:
            return {"status": "fail", "message": "run_command requires a command."}

        if self.dry_run:
            return {
                "status": "success",
                "message": f"Dry run: would execute command: {command}",
                "command": command,
            }

        try:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "fail",
                "message": f"Command timed out after {COMMAND_TIMEOUT_SECONDS} seconds.",
                "command": command,
            }
        except Exception as error:
            return {
                "status": "fail",
                "message": f"Command execution failed: {error}",
                "command": command,
            }

        status = "success" if completed.returncode == 0 else "fail"
        return {
            "status": status,
            "message": f"Command exited with code {completed.returncode}.",
            "command": command,
            "return_code": completed.returncode,
            "stdout_tail": _tail(completed.stdout),
            "stderr_tail": _tail(completed.stderr),
        }


def _tail(value: str, limit: int = 4000) -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[-limit:]
