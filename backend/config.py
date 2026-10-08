"""Paths, the one allowed model, and Portkey settings for the Campus Customs backend."""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
HW_DIR = BACKEND_DIR.parent
PROMPTS_DIR = BACKEND_DIR / "prompts"

DATA_DIR = HW_DIR / "data"
ORIGINAL_DB = DATA_DIR / "campus_customs.db"
WORKING_DB = Path(os.getenv("CAMPUS_DB_PATH", DATA_DIR / "campus_customs_new.db")).resolve()
REQUESTS_PATH = Path(os.getenv("CAMPUS_REQUESTS_PATH", DATA_DIR / "payment_requests.json")).resolve()
INCOMING_PATH = Path(os.getenv("CAMPUS_INCOMING_PATH", DATA_DIR / "incoming_stock.json")).resolve()

OUTPUT_DIR = HW_DIR / "output"
AUDIT_PATH = Path(os.getenv("CAMPUS_AUDIT_PATH", OUTPUT_DIR / "audit_trail.json")).resolve()
DRAFTS_PATH = Path(os.getenv("CAMPUS_DRAFTS_PATH", OUTPUT_DIR / "drafts.json")).resolve()

MCP_SERVER_SCRIPT = HW_DIR / "mcp_server" / "server.py"

# The only model any agent may use.
MODEL = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
# PORTKEY_API_KEY is read from hw5/.env (copy .env.example). For the original local setup,
# a .env one folder up (MGT409/.env) is used as a fallback. The key is never printed or logged.
ENV_FILE = HW_DIR / ".env"
PARENT_ENV_FILE = HW_DIR.parent / ".env"

# Token prices used to turn usage into dollars for the spend limit. The shop database
# has no model pricing, so these come from published gpt-6-luna standard API rates
# (USD per 1M tokens, checked 2026-10-08; e.g. https://openrouter.ai/openai/gpt-6-luna).
# Override with env vars if your Portkey/Azure contract bills differently.
PRICE_INPUT_PER_M = float(os.getenv("LUNA_PRICE_INPUT_PER_M", "0.10"))
PRICE_OUTPUT_PER_M = float(os.getenv("LUNA_PRICE_OUTPUT_PER_M", "0.50"))
SETTINGS_PATH = Path(os.getenv("CAMPUS_SETTINGS_PATH", DATA_DIR / "desk_settings.json")).resolve()
DEFAULT_SPEND_LIMIT_USD = 3.00

if WORKING_DB == ORIGINAL_DB.resolve():
    raise RuntimeError("The backend must use campus_customs_new.db, never the original.")


def portkey_api_key() -> str:
    load_dotenv(ENV_FILE)
    load_dotenv(PARENT_ENV_FILE)  # does not override a key already loaded
    key = os.getenv("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError(f"PORTKEY_API_KEY was not found. Copy .env.example to {ENV_FILE} and add your key.")
    return key
