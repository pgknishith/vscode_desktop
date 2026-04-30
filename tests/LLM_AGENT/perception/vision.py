import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None

from configs.settings import MIN_OCR_CONFIDENCE, SCREENSHOT_PATH, UI_TEXT_MATCH_THRESHOLD


OCRItem = Dict[str, object]


def extract_text(image_path: str | Path = SCREENSHOT_PATH) -> List[OCRItem]:
    image_path = Path(image_path)
    if pytesseract is None or Image is None or not image_path.exists():
        return []

    try:
        image = Image.open(image_path)
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except Exception:
        return []

    items: List[OCRItem] = []

    for index, raw_text in enumerate(data.get("text", [])):
        text = raw_text.strip()
        if not text:
            continue

        confidence = _safe_float(data["conf"][index])
        if confidence < MIN_OCR_CONFIDENCE:
            continue

        left = _safe_int(data["left"][index])
        top = _safe_int(data["top"][index])
        width = _safe_int(data["width"][index])
        height = _safe_int(data["height"][index])

        items.append(
            {
                "text": text,
                "confidence": confidence,
                "box": {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                },
                "center": {
                    "x": left + width // 2,
                    "y": top + height // 2,
                },
                "block_num": _safe_int(_data_value(data, "block_num", index)),
                "par_num": _safe_int(_data_value(data, "par_num", index)),
                "line_num": _safe_int(_data_value(data, "line_num", index)),
                "word_num": _safe_int(_data_value(data, "word_num", index)),
            }
        )

    return items


def locate_text(
    target: str,
    image_path: str | Path = SCREENSHOT_PATH,
    threshold: float = UI_TEXT_MATCH_THRESHOLD,
) -> Optional[Dict[str, object]]:
    target = target.strip()
    if not target:
        return None

    candidates = extract_text_candidates(image_path)
    best: Optional[Dict[str, object]] = None
    best_score = 0.0

    for candidate in candidates:
        score = _match_score(target, str(candidate["text"]))
        if score > best_score:
            best = candidate
            best_score = score

    if not best or best_score < threshold:
        return None

    best["score"] = round(best_score, 3)
    return best


def find_text(target: str, image_path: str | Path = SCREENSHOT_PATH) -> Optional[Tuple[int, int]]:
    match = locate_text(target, image_path)
    if not match:
        return None

    center = match["center"]
    return int(center["x"]), int(center["y"])


def extract_text_candidates(image_path: str | Path = SCREENSHOT_PATH) -> List[OCRItem]:
    return _candidate_items(extract_text(image_path))


def _candidate_items(items: List[OCRItem]) -> List[OCRItem]:
    candidates = list(items)
    lines: Dict[Tuple[int, int, int], List[OCRItem]] = {}

    for item in items:
        key = (
            int(item.get("block_num", 0)),
            int(item.get("par_num", 0)),
            int(item.get("line_num", 0)),
        )
        lines.setdefault(key, []).append(item)

    for line_items in lines.values():
        if len(line_items) <= 1:
            continue

        ordered = sorted(line_items, key=lambda item: int(item.get("word_num", 0)))
        candidates.append(_merge_line_items(ordered))

        # Also generate short adjacent phrases for button labels like "Sign in".
        for start in range(len(ordered)):
            for end in range(start + 2, min(len(ordered), start + 5) + 1):
                candidates.append(_merge_line_items(ordered[start:end]))

    return candidates


def _merge_line_items(items: List[OCRItem]) -> OCRItem:
    left = min(int(item["box"]["left"]) for item in items)
    top = min(int(item["box"]["top"]) for item in items)
    right = max(int(item["box"]["left"]) + int(item["box"]["width"]) for item in items)
    bottom = max(int(item["box"]["top"]) + int(item["box"]["height"]) for item in items)
    confidence = sum(float(item["confidence"]) for item in items) / len(items)

    return {
        "text": " ".join(str(item["text"]) for item in items),
        "confidence": round(confidence, 2),
        "box": {
            "left": left,
            "top": top,
            "width": right - left,
            "height": bottom - top,
        },
        "center": {
            "x": left + (right - left) // 2,
            "y": top + (bottom - top) // 2,
        },
        "block_num": items[0].get("block_num", 0),
        "par_num": items[0].get("par_num", 0),
        "line_num": items[0].get("line_num", 0),
        "word_num": items[0].get("word_num", 0),
    }


def _match_score(target: str, candidate: str) -> float:
    target_norm = _normalize_text(target)
    candidate_norm = _normalize_text(candidate)

    if not target_norm or not candidate_norm:
        return 0.0

    if target_norm == candidate_norm:
        return 1.0

    if target_norm in candidate_norm:
        return 0.96

    if candidate_norm in target_norm:
        return 0.86

    return SequenceMatcher(None, target_norm, candidate_norm).ratio()


def _normalize_text(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _data_value(data: Dict[str, List[object]], key: str, index: int) -> object:
    values = data.get(key, [])
    if index >= len(values):
        return 0
    return values[index]


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
