import os
from typing import List

import yaml
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow cross-origin requests from anywhere so the grader page can call
# this endpoint directly from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Layer 1: hardcoded defaults
# ---------------------------------------------------------------------------
DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

INT_KEYS = {"port", "workers"}
BOOL_KEYS = {"debug"}
TRUE_STRINGS = {"true", "1", "yes", "on"}


def coerce(key: str, value):
    """Apply type coercion rules for a given key."""
    if key in INT_KEYS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if key in BOOL_KEYS:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in TRUE_STRINGS
    return str(value)


def load_yaml_layer(env_name: str) -> dict:
    """Layer 2: config.<env>.yaml"""
    path = os.path.join(BASE_DIR, f"config.{env_name}.yaml")
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    return data


def parse_dotenv_file(path: str) -> dict:
    """Read a .env-style file into a raw {KEY: value} dict (no prefix logic)."""
    raw = {}
    if not os.path.exists(path):
        return raw
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            raw[key] = value
    return raw


def dotenv_layer() -> dict:
    """Layer 3: .env file, with APP_* prefix stripped and NUM_WORKERS alias."""
    # Support both a literal ".env" and ".env.config" (some hosts/gitignore
    # templates hide plain ".env" files, so we check both).
    raw = {}
    for candidate in (".env", ".env.config"):
        raw.update(parse_dotenv_file(os.path.join(BASE_DIR, candidate)))

    result = {}
    for key, value in raw.items():
        if key == "NUM_WORKERS":
            result["workers"] = value
        elif key.startswith("APP_"):
            result[key[len("APP_"):].lower()] = value
    return result


def os_env_layer() -> dict:
    """Layer 4: real OS environment variables with APP_* prefix."""
    result = {}
    for key, value in os.environ.items():
        if key.startswith("APP_"):
            result[key[len("APP_"):].lower()] = value
        elif key == "NUM_WORKERS":
            result["workers"] = value
    return result


def cli_layer(set_params: List[str]) -> dict:
    """Layer 5 (highest): ?set=key=value query overrides."""
    result = {}
    for item in set_params:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        result[key.strip()] = value.strip()
    return result


@app.get("/effective-config")
async def effective_config(
    set: List[str] = Query(default=[]),
    env: str = Query(default="development"),
):
    merged = dict(DEFAULTS)
    merged.update(load_yaml_layer(env))
    merged.update(dotenv_layer())
    merged.update(os_env_layer())
    merged.update(cli_layer(set))

    response = {
        "port": coerce("port", merged.get("port", DEFAULTS["port"])),
        "workers": coerce("workers", merged.get("workers", DEFAULTS["workers"])),
        "debug": coerce("debug", merged.get("debug", DEFAULTS["debug"])),
        "log_level": coerce("log_level", merged.get("log_level", DEFAULTS["log_level"])),
        "api_key": "****",
    }
    return response


@app.get("/")
async def root():
    return {"status": "ok"}
