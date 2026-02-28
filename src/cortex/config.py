from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Any, Dict, List

import yaml
from platformdirs import user_data_dir
from pydantic import BaseModel, Field


# -----------------------
# Config models
# -----------------------

class LLMConfig(BaseModel):
    enabled: bool = False
    timeout: int = 60

    primary_model_path: str = "models/qwen2.5-instruct.gguf"
    fallback_model_path: str = "models/phi-3.5-mini-instruct.gguf"

    n_ctx: int = 4096
    max_tokens: int = 512
    temperature: float = 0.1


class GPUConfig(BaseModel):
    enable: bool = True
    n_gpu_layers: int = 0


class SecureConfig(BaseModel):
    enabled: bool = False
    password_hash: Optional[str] = None
    allowed_paths: List[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    gpu: GPUConfig = Field(default_factory=GPUConfig)
    secure: SecureConfig = Field(default_factory=SecureConfig)

    # Optional future-proof keys (safe defaults)
    secure_mode: bool = False
    allow_browser: bool = False
    allow_email: bool = False

    # Filesystem sandbox (Phase 1.x safe default)
    sandbox_root: str = "."


# -----------------------
# Loading logic
# -----------------------

_CONFIG_CACHE: Optional[AppConfig] = None


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge override into base recursively."""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _candidate_paths() -> list[Path]:
    """
    Search order (most specific first):
    1) CORTEX_CONFIG env var
    2) ./config.yaml (repo root / current working dir)
    3) user data dir (cross-platform) e.g. %APPDATA%/cortex/config.yaml
    """
    paths: list[Path] = []

    env_path = os.environ.get("CORTEX_CONFIG")
    if env_path:
        paths.append(Path(env_path))

    paths.append(Path.cwd() / "config.yaml")

    data_dir = Path(user_data_dir("cortex"))
    paths.append(data_dir / "config.yaml")

    return paths


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError(
            f"Config file must be a YAML mapping (dict), got: {type(data)}"
        )
    return data


def get_config(force_reload: bool = False) -> AppConfig:
    """
    Returns a validated AppConfig.
    Cached by default.
    """
    global _CONFIG_CACHE

    if _CONFIG_CACHE is not None and not force_reload:
        return _CONFIG_CACHE

    # defaults from model -> dict
    default_cfg = AppConfig().model_dump()

    # merge in first config file found (highest priority)
    merged = default_cfg
    chosen_path: Optional[Path] = None
    for p in _candidate_paths():
        if p.exists():
            merged = _deep_merge(merged, _load_yaml(p))
            chosen_path = p
            break

    # ensure secure block exists (backward compatibility)
    if "secure" not in merged or merged["secure"] is None:
        merged["secure"] = SecureConfig().model_dump()

    cfg = AppConfig.model_validate(merged)

    # Basic normalization: expand paths
    cfg.llm.primary_model_path = str(
        Path(cfg.llm.primary_model_path).expanduser()
    )
    cfg.llm.fallback_model_path = str(
        Path(cfg.llm.fallback_model_path).expanduser()
    )
    cfg.sandbox_root = str(Path(cfg.sandbox_root).expanduser())

    # normalize secure.allowed_paths
    cfg.secure.allowed_paths = [
        str(Path(p).expanduser()) for p in cfg.secure.allowed_paths
    ]

    _CONFIG_CACHE = cfg
    return cfg


def get_config_path() -> Optional[str]:
    """Returns the path actually used, if any."""
    for p in _candidate_paths():
        if p.exists():
            return str(p)
    return None


def save_config(cfg: AppConfig, path: Optional[Path] = None) -> None:
    """
    Persist config (including secure block) back to YAML.
    """
    if path is None:
        data_dir = Path(user_data_dir("cortex"))
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "config.yaml"

    data = cfg.model_dump()
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
