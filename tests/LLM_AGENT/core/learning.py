import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    requests = None

from configs.settings import (
    EXPERTISE_PATH,
    KNOWLEDGE_PATH,
    LEARNING_ENABLED,
    LEARNING_PATHS_PATH,
    WEB_LEARNING_ALLOWED_DOMAINS,
    WEB_LEARNING_ENABLED,
    WEB_LEARNING_MAX_CHARS,
    WEB_LEARNING_SOURCES,
    WEB_LEARNING_TIMEOUT_SECONDS,
)
from core.model_client import OllamaClient


class LearningSystem:
    def __init__(self, model_client: OllamaClient | None = None):
        self.model_client = model_client or OllamaClient()
        self.knowledge = KnowledgeBase()
        self.paths = LearningPathManager(self.model_client)
        self.expertise = ExpertiseTracker()

    def prepare(self, goal: str) -> Dict[str, Any]:
        topic = infer_topic(goal)
        related_knowledge = self.knowledge.search(topic, limit=5)
        current_profile = self.expertise.profile_for(topic)
        learning_path = self.paths.path_for(topic, related_knowledge, current_profile)
        web_learning = {"status": "skipped", "message": "Web learning is disabled."}

        if LEARNING_ENABLED and WEB_LEARNING_ENABLED and WEB_LEARNING_SOURCES:
            web_learning = self.learn_topic(topic, list(WEB_LEARNING_SOURCES))
            related_knowledge = self.knowledge.search(topic, limit=5)
            learning_path = self.paths.path_for(topic, related_knowledge, current_profile)

        return {
            "enabled": LEARNING_ENABLED,
            "topic": topic,
            "profile": current_profile,
            "knowledge": related_knowledge,
            "learning_path": learning_path,
            "web_learning": web_learning,
        }

    def learn_topic(self, topic: str, sources: List[str] | None = None) -> Dict[str, Any]:
        if not LEARNING_ENABLED:
            return {"status": "disabled", "message": "Learning is disabled.", "entries": []}

        manual_sources = bool(sources)
        sources = sources or list(WEB_LEARNING_SOURCES)
        learner = WebLearner(self.model_client)
        result = learner.learn(topic, sources, manual=manual_sources)
        entries = result.get("entries", [])
        for entry in entries:
            self.knowledge.add(entry)

        related = self.knowledge.search(topic, limit=8)
        result["learning_path"] = self.paths.path_for(
            topic,
            related,
            self.expertise.profile_for(topic),
        )
        result["profile"] = self.expertise.profile_for(topic)
        return result

    def record_goal(self, goal: str, result: Dict[str, Any]) -> Dict[str, Any]:
        return self.expertise.record(goal, result, self.knowledge.search(infer_topic(goal), limit=20))

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": LEARNING_ENABLED,
            "web_learning_enabled": WEB_LEARNING_ENABLED,
            "knowledge_entries": len(self.knowledge.data.get("entries", [])),
            "learning_paths": len(self.paths.data.get("paths", {})),
            "expertise_profiles": len(self.expertise.data.get("profiles", {})),
            "allowed_web_domains": list(WEB_LEARNING_ALLOWED_DOMAINS),
        }


class KnowledgeBase:
    def __init__(self, path: str | Path = KNOWLEDGE_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load({"entries": []})

    def add(self, entry: Dict[str, Any]) -> None:
        entry["id"] = entry.get("id") or f"knowledge-{len(self.data['entries']) + 1}"
        entry["learned_at"] = entry.get("learned_at") or _now()
        self.data["entries"].append(entry)
        self._save()

    def search(self, topic: str, limit: int = 5) -> List[Dict[str, Any]]:
        tokens = set(_tokens(topic))
        scored = []
        for entry in self.data.get("entries", []):
            haystack = " ".join(
                [
                    str(entry.get("topic", "")),
                    str(entry.get("title", "")),
                    str(entry.get("summary", "")),
                    " ".join(str(item) for item in entry.get("facts", [])),
                ]
            ).lower()
            score = sum(1 for token in tokens if token in haystack)
            if score:
                scored.append((score, entry))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    def _load(self, fallback: Dict[str, Any]) -> Dict[str, Any]:
        if not self.path.exists():
            return fallback
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else fallback
        except (json.JSONDecodeError, OSError):
            return fallback

    def _save(self) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2, default=str)


class WebLearner:
    def __init__(self, model_client: OllamaClient | None = None):
        self.model_client = model_client or OllamaClient()

    def learn(self, topic: str, sources: List[str], manual: bool = False) -> Dict[str, Any]:
        if not WEB_LEARNING_ENABLED and not manual:
            return {"status": "disabled", "message": "Web learning is disabled.", "entries": []}

        if requests is None:
            return {"status": "unavailable", "message": "Install requests to learn from web pages.", "entries": []}

        entries = []
        errors = []
        for source in sources:
            if not self._allowed(source):
                errors.append({"source": source, "message": "Domain is not allowlisted."})
                continue

            fetched = self._fetch(source)
            if fetched["status"] != "success":
                errors.append({"source": source, "message": fetched["message"]})
                continue

            entries.append(self._summarize(topic, source, fetched["title"], fetched["text"]))

        status = "success" if entries else "empty"
        return {
            "status": status,
            "topic": topic,
            "entries": entries,
            "errors": errors,
        }

    def _allowed(self, source: str) -> bool:
        host = urlparse(source).netloc.lower()
        return any(host == domain or host.endswith(f".{domain}") for domain in WEB_LEARNING_ALLOWED_DOMAINS)

    def _fetch(self, source: str) -> Dict[str, str]:
        try:
            response = requests.get(source, timeout=WEB_LEARNING_TIMEOUT_SECONDS)
            response.raise_for_status()
        except Exception as error:
            return {"status": "fail", "message": str(error), "title": "", "text": ""}

        parser = TextHTMLParser()
        parser.feed(response.text[:WEB_LEARNING_MAX_CHARS])
        text = _clean_text(parser.text())
        return {
            "status": "success",
            "message": "Fetched source.",
            "title": parser.title or source,
            "text": text[:WEB_LEARNING_MAX_CHARS],
        }

    def _summarize(self, topic: str, source: str, title: str, text: str) -> Dict[str, Any]:
        model_summary = self._model_summary(topic, title, text)
        if model_summary:
            return {
                "topic": topic,
                "source": source,
                "title": title,
                "summary": model_summary.get("summary", ""),
                "facts": model_summary.get("facts", []),
                "confidence": "medium",
            }

        facts = _sentences(text)[:5]
        return {
            "topic": topic,
            "source": source,
            "title": title,
            "summary": " ".join(facts[:2]),
            "facts": facts,
            "confidence": "low",
        }

    def _model_summary(self, topic: str, title: str, text: str) -> Dict[str, Any]:
        if not self.model_client.enabled:
            return {}

        prompt = f"""
Summarize this source for an AI IT engineer learning path.

Topic: {topic}
Title: {title}

Source text:
{text[:6000]}

Return only JSON:
{{
  "summary": "short summary",
  "facts": ["actionable fact 1", "actionable fact 2"]
}}
""".strip()
        return self.model_client.generate_json(prompt) or {}


class LearningPathManager:
    def __init__(
        self,
        model_client: OllamaClient | None = None,
        path: str | Path = LEARNING_PATHS_PATH,
    ):
        self.model_client = model_client or OllamaClient()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load({"paths": {}})

    def path_for(
        self,
        topic: str,
        knowledge: List[Dict[str, Any]],
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        key = _key(topic)
        existing = self.data["paths"].get(key)
        if existing:
            return existing

        generated = self._generate(topic, knowledge, profile)
        self.data["paths"][key] = generated
        self._save()
        return generated

    def _generate(
        self,
        topic: str,
        knowledge: List[Dict[str, Any]],
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self.model_client.enabled:
            prompt = f"""
Create a practical learning path for an AI IT engineer.

Topic: {topic}
Current profile:
{json.dumps(profile, indent=2, default=str)}

Known material:
{json.dumps(knowledge[:5], indent=2, default=str)}

Return only JSON:
{{
  "topic": "{topic}",
  "stages": [
    {{"name": "stage name", "objective": "what to master", "status": "pending"}}
  ]
}}
""".strip()
            generated = self.model_client.generate_json(prompt)
            if generated and isinstance(generated.get("stages"), list):
                generated["topic"] = topic
                generated["created_at"] = _now()
                return generated

        return {
            "topic": topic,
            "created_at": _now(),
            "stages": [
                {
                    "name": "Fundamentals",
                    "objective": f"Understand core concepts and vocabulary for {topic}.",
                    "status": "pending",
                },
                {
                    "name": "Diagnostics",
                    "objective": f"Learn safe read-only checks and signals for {topic}.",
                    "status": "pending",
                },
                {
                    "name": "Remediation",
                    "objective": f"Learn reversible fixes and escalation points for {topic}.",
                    "status": "pending",
                },
                {
                    "name": "Verification",
                    "objective": f"Learn how to confirm that {topic} work is actually resolved.",
                    "status": "pending",
                },
            ],
        }

    def _load(self, fallback: Dict[str, Any]) -> Dict[str, Any]:
        if not self.path.exists():
            return fallback
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else fallback
        except (json.JSONDecodeError, OSError):
            return fallback

    def _save(self) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2, default=str)


class ExpertiseTracker:
    def __init__(self, path: str | Path = EXPERTISE_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load({"profiles": {}})

    def profile_for(self, topic: str) -> Dict[str, Any]:
        key = _key(topic)
        return self.data["profiles"].get(
            key,
            {
                "topic": topic,
                "attempts": 0,
                "successes": 0,
                "blocks": 0,
                "expertise_level": "new",
                "last_used_at": "",
            },
        )

    def record(
        self,
        goal: str,
        result: Dict[str, Any],
        knowledge: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        topic = infer_topic(goal)
        key = _key(topic)
        profile = self.profile_for(topic)
        profile["attempts"] += 1
        profile["last_goal"] = goal
        profile["last_used_at"] = _now()

        if result.get("status") == "done":
            profile["successes"] += 1
        elif result.get("status") in {"blocked", "max_steps_reached"}:
            profile["blocks"] += 1

        profile["knowledge_entries"] = len(knowledge)
        profile["expertise_level"] = self._level(profile)
        self.data["profiles"][key] = profile
        self._save()
        return profile

    def _level(self, profile: Dict[str, Any]) -> str:
        attempts = int(profile.get("attempts", 0))
        successes = int(profile.get("successes", 0))
        knowledge_entries = int(profile.get("knowledge_entries", 0))
        success_rate = successes / attempts if attempts else 0

        if attempts >= 20 and success_rate >= 0.85 and knowledge_entries >= 8:
            return "expert"
        if attempts >= 8 and success_rate >= 0.7 and knowledge_entries >= 3:
            return "practitioner"
        if attempts >= 3:
            return "apprentice"
        return "new"

    def _load(self, fallback: Dict[str, Any]) -> Dict[str, Any]:
        if not self.path.exists():
            return fallback
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else fallback
        except (json.JSONDecodeError, OSError):
            return fallback

    def _save(self) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2, default=str)


class TextHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []
        self.title = ""
        self._in_title = False
        self._skip = False

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = True
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        clean = data.strip()
        if not clean:
            return
        if self._in_title:
            self.title = clean
        else:
            self.parts.append(clean)

    def text(self) -> str:
        return " ".join(self.parts)


def infer_topic(goal: str) -> str:
    lowered = goal.lower()
    if any(word in lowered for word in {"server", "service", "port", "network", "nginx", "apache"}):
        return "server operations"
    if any(word in lowered for word in {"python", "pip", "venv", "package"}):
        return "python development"
    if any(word in lowered for word in {"docker", "container", "image"}):
        return "docker operations"
    if any(word in lowered for word in {"kubernetes", "kubectl", "pod"}):
        return "kubernetes operations"
    if any(word in lowered for word in {"database", "postgres", "mysql", "redis"}):
        return "database operations"
    return "general IT automation"


def _tokens(value: str) -> List[str]:
    return [token for token in re.split(r"[^a-z0-9]+", value.lower()) if len(token) > 2]


def _key(value: str) -> str:
    return "-".join(_tokens(value)) or "general"


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _sentences(value: str) -> List[str]:
    pieces = re.split(r"(?<=[.!?])\s+", value)
    return [piece.strip() for piece in pieces if len(piece.strip()) > 40]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
