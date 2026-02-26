from __future__ import annotations

import time
from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel

from cortex.runtime.config import load_config, write_config, config_path
from cortex.runtime.session import new_session
from cortex.runtime.logging import session_log_path, append_jsonl
from cortex.llm.provider_llamacpp import LlamaCppProvider

app = typer.Typer(help="LLM runtime controls (status/bench/gpu layers).")
console = Console()


# -------------------------------------------------------------------
# Utilities
# -------------------------------------------------------------------

def _llama_available() -> bool:
    try:
        from llama_cpp import Llama  # noqa: F401
        return True
    except Exception:
        return False


def _project_root() -> Path:
    """
    Resolve project root (repo root).
    Assumes this file is: src/cortex/cli_llm.py
    """
    return Path(__file__).resolve().parents[2]


def resolve_model_path(p: str) -> str:
    """
    Resolve model path safely without requiring absolute paths in config.
    Resolution order:
      1) Absolute path
      2) Relative to project root
    """
    path = Path(p)

    # Absolute path
    if path.is_absolute() and path.exists():
        return str(path)

    # Relative to project root
    candidate = (_project_root() / path).resolve()
    if candidate.exists():
        return str(candidate)

    raise typer.BadParameter(f"Model path does not exist: {p}")


# -------------------------------------------------------------------
# Commands
# -------------------------------------------------------------------

@app.command("status")
def status() -> None:
    cfg = load_config()
    llm = cfg.get("llm") or {}
    gpu = cfg.get("gpu") or {}

    console.print(Panel.fit("LLM Status", title="cortex"))
    console.print(f"[dim]Config:[/dim] {config_path()}")
    console.print(f"llama_cpp_available: {_llama_available()}")
    console.print(f"llm.enabled: {llm.get('enabled', False)}")
    console.print(f"primary_model_path: {llm.get('primary_model_path')}")
    console.print(f"fallback_model_path: {llm.get('fallback_model_path')}")
    console.print(f"n_ctx: {llm.get('n_ctx')}")
    console.print(f"max_tokens: {llm.get('max_tokens')}")
    console.print(f"temperature: {llm.get('temperature')}")
    console.print(
        f"timeout_seconds: {llm.get('timeout_seconds') or llm.get('timeout')}")
    console.print(f"gpu.enable: {gpu.get('enable', False)}")
    console.print(f"gpu.n_gpu_layers: {gpu.get('n_gpu_layers', 0)}")
    console.print(
        f"effective_gpu_layers: {gpu.get('n_gpu_layers', 0) if gpu.get('enable') else 0}"
    )


@app.command("set-gpu-layers")
def set_gpu_layers(
    n: int = typer.Argument(...,
                            help="GPU layers (0 = CPU). Safe range: 0..200")
) -> None:
    if n < 0 or n > 200:
        raise typer.BadParameter("n must be between 0 and 200")

    cfg = load_config()
    cfg.setdefault("gpu", {})
    cfg["gpu"]["n_gpu_layers"] = int(n)

    p = write_config(cfg)
    console.print(
        Panel.fit(f"Updated gpu.n_gpu_layers={n}\nWrote: {p}", title="cortex")
    )


@app.command("bench")
def bench(
    runs: int = typer.Option(3, help="Number of runs"),
    use_fallback: bool = typer.Option(False, help="Bench fallback model"),
) -> None:
    cfg = load_config()
    llm = cfg.get("llm") or {}
    gpu = cfg.get("gpu") or {}

    if not llm.get("enabled", False):
        raise typer.BadParameter("LLM disabled (llm.enabled=false).")

    if not _llama_available():
        raise typer.BadParameter(
            "llama-cpp-python not available. Install it to bench."
        )

    raw_model_path = (
        llm.get("fallback_model_path")
        if use_fallback
        else llm.get("primary_model_path")
    )

    if not raw_model_path:
        raise typer.BadParameter("Model path missing in config.yaml.")

    model_path = resolve_model_path(raw_model_path)

    n_ctx = int(llm.get("n_ctx") or 2048)
    timeout_seconds = int(llm.get("timeout_seconds")
                          or llm.get("timeout") or 60)
    max_tokens = int(llm.get("max_tokens") or 96)
    temperature = float(llm.get("temperature") or 0.0)
    n_gpu_layers = int(gpu.get("n_gpu_layers")
                       or 0) if gpu.get("enable") else 0

    session = new_session()
    logp = session_log_path(session.session_id)

    append_jsonl(
        logp,
        {
            "event": "bench_start",
            "model": model_path,
            "runs": runs,
            "n_gpu_layers": n_gpu_layers,
        },
    )

    prompt = "Output ONLY JSON.\n<json>\n" + '{"ok": true}\n'

    # ---- Load provider (GPU fallback supported) ----
    t_load0 = time.time()
    try:
        provider = LlamaCppProvider(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            timeout=timeout_seconds,
        )
        load_err = None
    except Exception as e:
        provider = None
        load_err = e

    load_sec = time.time() - t_load0

    if provider is None and n_gpu_layers > 0:
        append_jsonl(logp, {"event": "bench_gpu_fallback",
                     "reason": str(load_err)})
        provider = LlamaCppProvider(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=0,
            timeout=timeout_seconds,
        )

    if provider is None:
        append_jsonl(logp, {"event": "bench_abort", "error": str(load_err)})
        raise RuntimeError(f"Bench abort: failed to load model: {load_err}")

    # ---- Run benchmark ----
    times = []
    for _ in range(runs):
        t0 = time.time()
        _ = provider.generate(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            log_path=logp,
            stop=["</json>"],
        ).text
        times.append(time.time() - t0)

    avg = sum(times) / len(times)
    mn = min(times)
    mx = max(times)

    append_jsonl(
        logp,
        {
            "event": "bench_result",
            "model": model_path,
            "load_sec": round(load_sec, 3),
            "avg_sec": round(avg, 3),
            "min_sec": round(mn, 3),
            "max_sec": round(mx, 3),
        },
    )

    console.print(
        Panel.fit("LLM Bench", title=f"session {session.session_id}"))
    console.print(f"model: {model_path}")
    console.print(f"gpu_layers_requested: {n_gpu_layers}")
    console.print(f"load_sec: {load_sec:.3f}")
    console.print(f"runs: {runs}")
    console.print(
        f"avg_sec: {avg:.3f} | min_sec: {mn:.3f} | max_sec: {mx:.3f}")
