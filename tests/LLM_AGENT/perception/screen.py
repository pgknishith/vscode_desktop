from pathlib import Path
from typing import Any, Dict

try:
    import pyautogui
except ImportError:
    pyautogui = None

from configs.settings import SCREENSHOT_PATH
from perception.vision import extract_text, extract_text_candidates


def capture_screen(path: str | Path = SCREENSHOT_PATH) -> str:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if pyautogui is None:
        return str(output_path)

    try:
        screenshot = pyautogui.screenshot()
        screenshot.save(output_path)
    except Exception:
        return str(output_path)

    return str(output_path)


def analyze_screen(path: str | Path = SCREENSHOT_PATH) -> Dict[str, Any]:
    screenshot_path = Path(path)
    text_items = extract_text(path)
    candidates = extract_text_candidates(path)
    phrases = _unique(
        str(item["text"])
        for item in candidates
        if " " in str(item.get("text", "")).strip()
    )
    return {
        "screenshot": str(screenshot_path),
        "screenshot_exists": screenshot_path.exists(),
        "text": [item["text"] for item in text_items],
        "phrases": phrases,
        "ocr": text_items,
    }


def _unique(values):
    seen = set()
    unique_values = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values
