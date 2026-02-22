# src/cortex/llm/json_extract.py
from __future__ import annotations

import json
from typing import Any, Dict


def extract_first_json_object(text: str) -> Dict[str, Any]:
    if "<json>" in text:
        start = text.find("<json>") + len("<json>")
        end = text.rfind("</json>")
        blob = text[start:end].strip() if end != -1 else text[start:].strip()

        # parse object inside
        first = blob.find("{")
        last = blob.rfind("}")
        if first != -1 and last != -1 and last > first:
            return json.loads(blob[first:last + 1])

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM output")

    return json.loads(text[start:end + 1])
