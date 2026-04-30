from typing import Any, Dict, Optional

try:
    import requests
except ImportError:
    requests = None

from configs.settings import MODEL, OLLAMA_URL, REQUEST_TIMEOUT_SECONDS
from core.contracts import extract_json_object


class OllamaClient:
    def __init__(
        self,
        url: str = OLLAMA_URL,
        model: str = MODEL,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    ):
        self.url = url
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.model and requests is not None)

    def generate_text(self, prompt: str) -> str:
        if not self.enabled:
            return ""

        try:
            response = requests.post(
                self.url,
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return str(response.json().get("response", ""))
        except Exception:
            return ""

    def generate_json(self, prompt: str) -> Optional[Dict[str, Any]]:
        return extract_json_object(self.generate_text(prompt))
