"""Configuration constants, paths, and thresholds."""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env if present
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip("\"'"))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RULEBOOK_PATH = BASE_DIR / "rulebook.json"
PLAYBOOK_PATH = BASE_DIR / "Clear Tax_DPA.docx"
CREDS_PATH = BASE_DIR / "credentials.json"
DB_PATH = BASE_DIR / "review.db"

# ---------------------------------------------------------------------------
# Embedding & Matching Thresholds
# ---------------------------------------------------------------------------
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-base-en-v1.5")
EMBED_MODEL_FALLBACK = "all-MiniLM-L6-v2"
MATCH_THRESHOLD_STRONG = 0.70
MATCH_THRESHOLD_PARTIAL = 0.45
RULE_MATCH_THRESHOLD = 0.58
KEYWORD_BOOST = 0.08

# ---------------------------------------------------------------------------
# LLM Settings
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MODEL = "claude-sonnet-4-20250514"

# ---------------------------------------------------------------------------
# Slack Notifications
# ---------------------------------------------------------------------------
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
