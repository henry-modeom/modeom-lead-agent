"""Configuration lue depuis les variables d'environnement (fichier .env accepté)."""

import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


ROOT = Path(__file__).resolve().parent.parent
_load_dotenv(ROOT / ".env")

MODEL = os.getenv("LEAD_AGENT_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("LEAD_AGENT_EFFORT", "medium")
MAX_TURNS = int(os.getenv("LEAD_AGENT_MAX_TURNS", "40"))
MAX_WEB_SEARCHES = int(os.getenv("LEAD_AGENT_MAX_WEB_SEARCHES", "40"))
DB_PATH = Path(os.getenv("LEAD_AGENT_DB", str(ROOT / "leads.db")))
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
