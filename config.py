"""
config.py

SightEngine setup   → sign up at https://sightengine.com, find keys at
                      https://dashboard.sightengine.com/api-credentials
"""

import os
from dotenv import load_dotenv

# Load variables from .env into os.environ
# Looks for .env in the same directory as this file
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def _require(key: str) -> str:
    """Read a required env variable or raise a clear error."""
    val = os.environ.get(key, "").strip()
    if not val or val.startswith("<"):
        raise EnvironmentError(
            f"Missing or unconfigured environment variable: {key}\n"
            f"Copy .env.example → .env and fill in the value for {key}."
        )
    return val


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


# ── MongoDB ────────────────────────────────────────────────────────────────────
MONGO_URI = _require("MONGO_URI")

# ── Auth ───────────────────────────────────────────────────────────────────────
SECRET_KEY             = _optional("SECRET_KEY", "factguard-dev-secret-change-me")
TOKEN_EXPIRY_SECONDS   = 60 * 60 * 24   # 24 hours

# ── SightEngine ────────────────────────────────────────────────────────────────
SIGHTENGINE_API_USER   = _require("SIGHTENGINE_API_USER")
SIGHTENGINE_API_SECRET = _require("SIGHTENGINE_API_SECRET")
SIGHTENGINE_URL        = "https://api.sightengine.com/1.0/check.json"

# Maximum number of article images to analyse per scan (keeps API costs low)
MAX_IMAGES_PER_SCAN    = 2
