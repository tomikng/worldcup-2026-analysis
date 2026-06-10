"""Shared football-data.org client helpers. Stdlib only."""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://api.football-data.org/v4"
COMPETITION = "WC"
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_TOKEN = 2


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_token() -> str | None:
    """Token from FOOTBALL_DATA_TOKEN env var, falling back to repo .env file."""
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if token:
        return token
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("FOOTBALL_DATA_TOKEN="):
                value = line.split("=", 1)[1].strip().strip("'\"")
                if value and value != "your-token-here":
                    return value
    return None


def fetch_matches(date: str, token: str) -> list[dict]:
    """All WC matches with kickoff on the given UTC date (YYYY-MM-DD)."""
    url = f"{API_BASE}/competitions/{COMPETITION}/matches?dateFrom={date}&dateTo={date}"
    req = urllib.request.Request(url, headers={"X-Auth-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"football-data.org HTTP {e.code}: {e.read().decode(errors='replace')[:200]}",
              file=sys.stderr)
        sys.exit(EXIT_ERROR)
    except urllib.error.URLError as e:
        print(f"football-data.org unreachable: {e.reason}", file=sys.stderr)
        sys.exit(EXIT_ERROR)
    return payload.get("matches", [])


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {path.relative_to(REPO_ROOT)}")


def require_token() -> str:
    token = load_token()
    if not token:
        print("FOOTBALL_DATA_TOKEN not set (env or .env). "
              "Agents should fall back to web research per CLAUDE.md.", file=sys.stderr)
        sys.exit(EXIT_NO_TOKEN)
    return token
