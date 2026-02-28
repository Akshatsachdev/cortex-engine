from __future__ import annotations

from pathlib import Path
import yaml
from platformdirs import user_config_dir, user_data_dir

APP_NAME = "cortex"

DEFAULT_CONFIG: dict = {
    "allowed_paths": [],
    "llm": {
        "enabled": False,
        "backend": "llama_cpp",
        "primary_model_path": "",
        "fallback_model_path": "",
        "n_ctx": 8192,
        "temperature": 0.1,
        "max_tokens": 1200,
        "timeout_seconds": 60,
    },
    "secure": {
        "enabled": False,
        "password_hash": None,
        "allowed_paths": [],
    },
    "gpu": {
        "enable": True,
        "n_gpu_layers": 40,
    },
    "tools": {
        "filesystem": {"enabled": True},
        "browser": {"enabled": False, "allowlist_domains": []},
        "email": {"enabled": False, "send_enabled": False},
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


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

    merged = _deep_merge(DEFAULT_CONFIG, loaded)
    return merged


def write_config(cfg: dict) -> Path:
    ensure_dirs()
    p = config_path()
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    return p


def effective_allowed_paths(cfg: dict) -> list[str]:
    secure = cfg.get("secure") or {}
    if secure.get("enabled"):
        return secure.get("allowed_paths") or []
    return cfg.get("allowed_paths") or []

# Backwards-compatible alias


def save_config(cfg):
    return write_config(cfg)
