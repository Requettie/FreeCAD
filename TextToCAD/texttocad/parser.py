"""
Text-to-CAD prompt parser.

Two-tier strategy:
  1. A deterministic, offline rule-based parser that recognises a domain
     keyword (rocket, jet, cpu, gpu, car ...) and pulls dimensions out of
     natural language ("a 2 metre rocket with 6 fins").
  2. An optional LLM path (``llm.py``) that, when an API key is present,
     can emit a full parameter dict for richer prompts. The rule-based
     parser is always the fallback so the feature works fully offline.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

from . import generators
from .spec import Design

# unit -> millimetres
_UNITS = {
    "mm": 1.0, "millimetre": 1.0, "millimeter": 1.0,
    "cm": 10.0, "centimetre": 10.0, "centimeter": 10.0,
    "m": 1000.0, "metre": 1000.0, "meter": 1000.0,
    "in": 25.4, "inch": 25.4, '"': 25.4,
    "ft": 304.8, "foot": 304.8, "feet": 304.8,
}

# Priority-ordered: the FIRST domain with a matching alias wins, so a
# specific "gpu" beats the generic "heatsink" in "GPU heatsink".
_DOMAIN_ALIASES = [
    ("rocket", ("rocket", "missile", "launch vehicle")),
    ("jet", ("turbofan", "turbine", "jet engine", "jet", "engine")),
    ("gpu", ("gpu", "graphics card", "video card")),
    ("cpu", ("cpu", "processor", "chip")),
    ("car", ("car", "sedan", "automobile", "vehicle")),
    ("propeller", ("propeller", "prop")),
    ("gear", ("gear", "cog", "sprocket")),
    # assemblies before the generic "bolt" fastener: "bolt flange" is a flange
    ("flange", ("flange",)),
    ("bracket", ("bracket", "angle bracket", "l-bracket")),
    ("enclosure", ("enclosure", "housing", "case")),
    ("bolt", ("bolt", "screw")),
    ("heatsink", ("heatsink", "heat sink", "cooler")),
]


def _to_mm(value: float, unit: str) -> float:
    return value * _UNITS.get(unit.lower(), 1.0)


def detect_domain(text: str) -> Optional[str]:
    t = text.lower()
    for domain, aliases in _DOMAIN_ALIASES:
        for alias in aliases:
            # word-boundary match so "car" does not fire inside "graphics card"
            if re.search(rf"\b{re.escape(alias)}\b", t):
                return domain
    return None


def _find_length(text: str, keywords: Tuple[str, ...],
                 fallback: bool = True) -> Optional[float]:
    """Find a number+unit near any keyword.

    With ``fallback`` (use only for the *primary* dimension) it also accepts
    the first bare number+unit anywhere. Secondary dimensions must pass
    ``fallback=False`` so they don't steal the primary's value.
    """
    unit_re = "|".join(re.escape(u) for u in _UNITS)
    num = rf"(?P<val>\d+(?:\.\d+)?)\s*(?P<unit>{unit_re})\b"
    best = None  # (gap, value): the number nearest the keyword wins

    def _consider(m):
        nonlocal best
        gap = len(m.group("gap"))
        val = _to_mm(float(m.group("val")), m.group("unit"))
        if best is None or gap < best[0]:
            best = (gap, val)

    for kw in keywords:
        k = re.escape(kw)
        # both orders; \D so a gap never swallows another number
        for m in re.finditer(rf"{num}(?P<gap>\D{{0,16}}?){k}", text):
            _consider(m)
        for m in re.finditer(rf"{k}(?P<gap>\D{{0,16}}?){num}", text):
            _consider(m)
    if best is not None:
        return best[1]
    if not fallback:
        return None
    m = re.search(num, text)
    return _to_mm(float(m.group("val")), m.group("unit")) if m else None


def _find_triple(text: str):
    """Parse an 'L x W x H [unit]' / 'L by W by H' dimension triple.

    The unit may appear once (trailing or after any number) and applies to all
    three; if absent, millimetres are assumed. Returns (l, w, h) in mm or None.
    """
    unit_re = "|".join(re.escape(u) for u in _UNITS)
    n = rf"(\d+(?:\.\d+)?)\s*({unit_re})?"   # number + optional unit (captured)
    sep = r"\s*(?:x|by|×|\*)\s*"
    m = re.search(rf"{n}{sep}{n}{sep}{n}", text)
    if not m:
        return None
    # a unit may sit after any of the three numbers; prefer the last given
    unit = m.group(6) or m.group(4) or m.group(2) or "mm"
    return tuple(_to_mm(float(m.group(i)), unit) for i in (1, 3, 5))


def _find_count(text: str, keyword: str) -> Optional[int]:
    m = re.search(rf"(\d+)\s*{keyword}", text) or \
        re.search(rf"{keyword}\D{{0,8}}(\d+)", text)
    return int(m.group(1)) if m else None


def parse(text: str) -> Tuple[str, Dict]:
    """Return (domain, params) extracted from a prompt. Raises if no domain."""
    domain = detect_domain(text)
    if domain is None:
        raise ValueError(
            "Could not identify what to build. Try naming a rocket, jet "
            "engine, CPU, GPU, heatsink, or car in your prompt."
        )
    t = text.lower()
    params: Dict = {}

    if domain == "rocket":
        L = _find_length(t, ("long", "length", "tall", "height"))
        if L:
            params["total_length"] = L
        dia = _find_length(t, ("diameter", "wide", "caliber", "calibre"),
                           fallback=False)
        if dia:
            params["body_diameter"] = dia
        fins = _find_count(t, "fin")
        if fins:
            params["fin_count"] = fins
        stages = _find_count(t, "stage")
        if stages:
            params["stages"] = stages

    elif domain == "jet":
        L = _find_length(t, ("long", "length"))
        if L:
            params["length"] = L
        fan = _find_length(t, ("fan", "diameter", "wide"), fallback=False)
        if fan:
            params["fan_diameter"] = fan
        blades = _find_count(t, "blade")
        if blades:
            params["blade_count"] = blades

    elif domain in ("cpu", "gpu", "heatsink"):
        base = _find_length(t, ("base", "wide", "size", "square"))
        if base:
            params["base"] = base
        fins = _find_count(t, "fin")
        if fins:
            params["fin_count"] = fins
        fh = _find_length(t, ("fin height", "tall", "high"), fallback=False)
        if fh:
            params["fin_height"] = fh

    elif domain == "car":
        triple = _find_triple(t)
        if triple:
            params["length"], params["width"], params["height"] = triple
        else:
            L = _find_length(t, ("long", "length"))
            if L:
                params["length"] = L
            W = _find_length(t, ("wide", "width"), fallback=False)
            if W:
                params["width"] = W
            H = _find_length(t, ("tall", "height", "high"), fallback=False)
            if H:
                params["height"] = H

    elif domain == "gear":
        teeth = _find_count(t, "teeth") or _find_count(t, "tooth")
        if teeth:
            params["teeth"] = teeth
        thk = _find_length(t, ("thick", "thickness", "wide"), fallback=False)
        if thk:
            params["thickness"] = thk

    elif domain == "propeller":
        blades = _find_count(t, "blade")
        if blades:
            params["blade_count"] = blades
        dia = _find_length(t, ("diameter", "wide"))
        if dia:
            params["diameter"] = dia

    elif domain == "bolt":
        L = _find_length(t, ("long", "length"))
        if L:
            params["length"] = L
        dia = _find_length(t, ("diameter", "wide"), fallback=False)
        if dia:
            params["diameter"] = dia

    elif domain == "flange":
        dia = _find_length(t, ("diameter", "wide"))
        if dia:
            params["diameter"] = dia
        bolts = _find_count(t, "bolt") or _find_count(t, "hole")
        if bolts:
            params["bolt_count"] = bolts

    elif domain == "enclosure":
        triple = _find_triple(t)
        if triple:
            params["length"], params["width"], params["height"] = triple
        else:
            L = _find_length(t, ("long", "length"))
            if L:
                params["length"] = L
            W = _find_length(t, ("wide", "width"), fallback=False)
            if W:
                params["width"] = W
            H = _find_length(t, ("tall", "height", "high"), fallback=False)
            if H:
                params["height"] = H

    return domain, params


def build_from_text(text: str, use_llm: bool = False) -> Design:
    """High-level entry point: prompt -> Design."""
    if use_llm:
        try:
            from . import llm
            domain, params = llm.parse(text)
        except Exception:
            domain, params = parse(text)
    else:
        domain, params = parse(text)

    fn = generators.REGISTRY[domain]
    # Drop params the generator does not accept (robustness against LLM noise)
    import inspect
    valid = set(inspect.signature(fn).parameters)
    params = {k: v for k, v in params.items() if k in valid}
    design = fn(**params)
    design.meta["prompt"] = text
    return design
