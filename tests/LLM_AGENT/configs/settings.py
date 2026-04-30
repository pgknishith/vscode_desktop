import os
from pathlib import Path


AGENT_VERSION = "2.4.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("AGENT_DATA_DIR", PROJECT_ROOT / "data"))
MEMORY_PATH = Path(os.getenv("AGENT_MEMORY_PATH", DATA_DIR / "memory.json"))
SCREENSHOT_PATH = Path(os.getenv("AGENT_SCREENSHOT_PATH", DATA_DIR / "screen.png"))
KNOWLEDGE_PATH = Path(os.getenv("AGENT_KNOWLEDGE_PATH", DATA_DIR / "knowledge.json"))
LEARNING_PATHS_PATH = Path(os.getenv("AGENT_LEARNING_PATHS_PATH", DATA_DIR / "learning_paths.json"))
EXPERTISE_PATH = Path(os.getenv("AGENT_EXPERTISE_PATH", DATA_DIR / "expertise.json"))

OLLAMA_URL = os.getenv("OLLAMA_URL", "")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))
ACTION_DELAY_SECONDS = float(os.getenv("AGENT_ACTION_DELAY_SECONDS", "0.25"))
DRY_RUN = os.getenv("AGENT_DRY_RUN", "0").strip().lower() in {"1", "true", "yes"}
MIN_OCR_CONFIDENCE = float(os.getenv("AGENT_MIN_OCR_CONFIDENCE", "35"))
UI_TEXT_MATCH_THRESHOLD = float(os.getenv("AGENT_UI_TEXT_MATCH_THRESHOLD", "0.72"))
COMMANDS_ENABLED = os.getenv("AGENT_COMMANDS_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
COMMAND_TIMEOUT_SECONDS = float(os.getenv("AGENT_COMMAND_TIMEOUT_SECONDS", "15"))
ALLOWED_COMMAND_PREFIXES = tuple(
    prefix.strip().lower()
    for prefix in os.getenv(
        "AGENT_ALLOWED_COMMAND_PREFIXES",
        "ipconfig,netstat,tasklist,where,python --version,python -V,pip --version",
    ).split(",")
    if prefix.strip()
)

LEARNING_ENABLED = os.getenv("AGENT_LEARNING_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
WEB_LEARNING_ENABLED = os.getenv("AGENT_WEB_LEARNING_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
WEB_LEARNING_TIMEOUT_SECONDS = float(os.getenv("AGENT_WEB_LEARNING_TIMEOUT_SECONDS", "10"))
WEB_LEARNING_MAX_CHARS = int(os.getenv("AGENT_WEB_LEARNING_MAX_CHARS", "12000"))
WEB_LEARNING_ALLOWED_DOMAINS = tuple(
    domain.strip().lower()
    for domain in os.getenv(
        "AGENT_WEB_LEARNING_ALLOWED_DOMAINS",
        "docs.python.org,learn.microsoft.com,developer.mozilla.org,nginx.org,apache.org,postgresql.org,mysql.com,redis.io,docker.com,kubernetes.io",
    ).split(",")
    if domain.strip()
)
WEB_LEARNING_SOURCES = tuple(
    source.strip()
    for source in os.getenv("AGENT_WEB_LEARNING_SOURCES", "").split(",")
    if source.strip()
)

VOICE_ENABLED = os.getenv("AGENT_VOICE_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
VOICE_RATE = int(os.getenv("AGENT_VOICE_RATE", "175"))
VOICE_VOLUME = float(os.getenv("AGENT_VOICE_VOLUME", "0.9"))
VOICE_NAME = os.getenv("AGENT_VOICE_NAME", "")
CONVERSATION_STYLE = os.getenv(
    "AGENT_CONVERSATION_STYLE",
    "warm, concise, realistic, and technically helpful",
)
