import os
import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- Layer 1: hardcoded defaults ----
DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

TYPE_MAP = {
    "port": "int",
    "workers": "int",
    "debug": "bool",
}


def coerce(key: str, value):
    kind = TYPE_MAP.get(key, "str")
    if kind == "int":
        return int(value)
    if kind == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    return str(value)


def load_yaml_layer(env_name: str = "development"):
    """Layer 2: environment-specific YAML file."""
    path = os.path.join(BASE_DIR, f"config.{env_name}.yaml")
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    return data


def parse_env_file(path: str):
    """Manually parse a .env file WITHOUT mutating os.environ,
    so it stays a distinct, lower-precedence layer from real OS env vars."""
    result = {}
    if not os.path.exists(path):
        return result
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")

            if k == "NUM_WORKERS":
                # Special alias, only defined for the .env layer
                result["workers"] = v
            elif k.startswith("APP_"):
                result[k[len("APP_"):].lower()] = v
            # any other unprefixed key is ignored per spec
    return result


def load_os_env_layer():
    """Layer 4: real OS-level environment variables with APP_ prefix."""
    result = {}
    for k, v in os.environ.items():
        if k.startswith("APP_"):
            result[k[len("APP_"):].lower()] = v
    return result


@app.get("/effective-config")
def effective_config(request: Request):
    env_name = os.environ.get("APP_ENV", "development")

    merged = dict(DEFAULTS)

    # Layer 2: config.<env>.yaml
    merged.update(load_yaml_layer(env_name))

    # Layer 3: .env file (project-local, not process env)
    dotenv_path = os.path.join(BASE_DIR, ".env")
    merged.update(parse_env_file(dotenv_path))

    # Layer 4: real OS environment variables (APP_ prefix)
    merged.update(load_os_env_layer())

    # Layer 5: CLI overrides via ?set=key=value (highest precedence)
    for raw in request.query_params.multi_items():
        if raw[0] != "set":
            continue
        pair = raw[1]
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        merged[k.strip()] = v.strip()

    # Type coercion
    coerced = {k: coerce(k, v) for k, v in merged.items()}

    # Mask secret
    coerced["api_key"] = "****"

    # Ensure the five required keys are present, in a stable shape
    output = {
        "port": coerced.get("port"),
        "workers": coerced.get("workers"),
        "debug": coerced.get("debug"),
        "log_level": coerced.get("log_level"),
        "api_key": "****",
    }
    return output


@app.get("/")
def health():
    return {"status": "ok"}
