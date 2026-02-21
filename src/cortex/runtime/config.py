from __future__ import annotations

from pathlib import Path
import yaml
from platformdirs import user_config_dir, user_data_dir

APP_NAME = "cortex"

DEFAULT_CONFIG: dict = {
    "secure_mode": False,
    "allowed_paths": [],  # empty => default HOME in code
    "llm": {
        "enabled": False,
        "backend": "llama_cpp",
        "primary_model_path": "",
        "fallback_model_path": "",
        "n_ctx": 8192,
        "temperature": 0.1,
        "max_tokens": 1200,
        "timeout_seconds": 60,
        "gpu": {
            "enable": True,
            "n_gpu_layers": 40,
        },
    },
    "tools": {
        "filesystem": {"enabled": True},
        "browser": {"enabled": False, "allowlist_domains": []},
        "email": {"enabled": False, "send_enabled": False},
    },
}


def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME))


def data_dir() -> Path:
    return Path(user_data_dir(APP_NAME))


def logs_dir() -> Path:
    return data_dir() / "logs"


def config_path() -> Path:
    return config_dir() / "config.yaml"


def ensure_dirs() -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    logs_dir().mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_dirs()
    p = config_path()
    if not p.exists():
        return DEFAULT_CONFIG.copy()
    with p.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    merged = DEFAULT_CONFIG.copy()
    merged.update(loaded)
    return merged


def write_config(cfg: dict) -> Path:
    ensure_dirs()
    p = config_path()
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    return p