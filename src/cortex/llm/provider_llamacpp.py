from __future__ import annotations
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cortex.runtime.logging import append_jsonl

try:
    from llama_cpp import Llama
except Exception:  # pragma: no cover
    Llama = None  # type: ignore


@dataclass
class LlamaCppGenResult:
    text: str
    model_path: str
    duration_sec: float


class LlamaCppProvider:
    """
    Thin wrapper around llama-cpp-python.
    Loads a GGUF model and generates a completion.
    """

    def __init__(
        self,
        model_path: str,
        n_ctx: int,
        n_gpu_layers: int,
        timeout: int,
    ):
        if Llama is None:
            raise RuntimeError(
                "llama-cpp-python is not installed or failed to import. "
                "Install it to enable LLM planning."
            )

        self.model_path = model_path
        self.timeout = timeout

        # NOTE: timeout isn't enforced at llama-cpp layer here (Phase 1.3).
        # We'll enforce timeouts in Phase 1.4/1.5 with guards.
        self._llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )

    def generate(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        log_path: Path,
        stop: Optional[list[str]] = None,
    ) -> LlamaCppGenResult:
        append_jsonl(log_path, {"type": "llm_start",
                     "model": self.model_path})

        t0 = time.time()
        try:
            out = self._llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop or [],
            )
            dt = time.time() - t0

            # Soft timeout guard
            if self.timeout and dt > self.timeout:
                append_jsonl(
                    log_path,
                    {
                        "type": "llm_error",
                        "model": self.model_path,
                        "error": f"timeout_exceeded (dt={round(dt, 3)}s > timeout={self.timeout}s)",
                    },
                )
                raise TimeoutError(
                    f"LLM generation exceeded timeout={self.timeout}s (dt={dt:.3f}s)"
                )

            text = out["choices"][0]["text"]

            append_jsonl(
                log_path,
                {
                    "type": "llm_success",
                    "model": self.model_path,
                    "duration_sec": round(dt, 3),
                },
            )

            return LlamaCppGenResult(text=text, model_path=self.model_path, duration_sec=dt)

        except Exception as e:
            dt = time.time() - t0
            append_jsonl(
                log_path,
                {
                    "type": "llm_error",
                    "model": self.model_path,
                    "duration_sec": round(dt, 3),
                    "error": str(e),
                },
            )
            raise
