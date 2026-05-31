"""
Optional LLM-backed prompt understanding.

If ANTHROPIC_API_KEY is set and the ``anthropic`` SDK is installed, this asks
Claude to map a free-form prompt to (domain, params). Otherwise it raises and
the caller falls back to the deterministic rule-based parser in ``parser.py``.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Tuple

from . import generators

_SYSTEM = (
    "You translate a natural-language CAD request into structured parameters. "
    "Reply with ONLY a JSON object: {\"domain\": <one of "
    + ", ".join(sorted(set(generators.REGISTRY))) +
    ">, \"params\": {<numeric params in millimetres / integer counts>}}. "
    "Valid params per domain: "
    "rocket{total_length,body_diameter,fin_count,stages}; "
    "jet{length,fan_diameter,blade_count}; "
    "cpu/gpu/heatsink{base,fin_count,fin_height}; "
    "car{length,width,height,wheel_radius}. "
    "Omit params you cannot infer. No prose."
)


def parse(text: str) -> Tuple[str, Dict]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    import anthropic
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=os.environ.get("TEXTTOCAD_MODEL", "claude-sonnet-4-5"),
        max_tokens=400,
        system=_SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    # tolerate code fences
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(raw)
    domain = data["domain"]
    if domain not in generators.REGISTRY:
        raise ValueError(f"LLM returned unknown domain: {domain}")
    return domain, dict(data.get("params", {}))
