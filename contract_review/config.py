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
PLAYBOOK_PATH = BASE_DIR / "ClearTax_DPA.md"
CREDS_PATH = BASE_DIR / "credentials.json"
DB_PATH = BASE_DIR / "review.db"

# ---------------------------------------------------------------------------
# LLM Settings
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MODEL = "claude-opus-4-6"

# ---------------------------------------------------------------------------
# Email (SMTP)
# ---------------------------------------------------------------------------
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")

# ---------------------------------------------------------------------------
# Slack Notifications
# ---------------------------------------------------------------------------
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
