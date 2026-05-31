"""
Pure-Python tests — run WITHOUT FreeCAD:  python -m pytest TextToCAD/tests
(or plain `python TextToCAD/tests/test_core.py`).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from texttocad import parser, generators  # noqa: E402
from texttocad.spec import Box, Cone, Cylinder  # noqa: E402


def _check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_domain_detection():
    _check(parser.detect_domain("build me a rocket") == "rocket", "rocket")
    _check(parser.detect_domain("a turbofan jet engine") == "jet", "jet")
    _check(parser.detect_domain("graphics card cooler") == "gpu", "gpu")
    _check(parser.detect_domain("a fast sedan") == "car", "car")
    _check(parser.detect_domain("a poem") is None, "no domain")


def test_unit_parsing():
    dom, p = parser.parse("a 2 metre rocket, 150 mm diameter, 6 fins, 2 stages")
    _check(dom == "rocket", "domain")
    _check(p["total_length"] == 2000.0, f"len {p}")
    _check(p["body_diameter"] == 150.0, f"dia {p}")
    _check(p["fin_count"] == 6, f"fins {p}")
    _check(p["stages"] == 2, f"stages {p}")


def test_rocket_geometry():
    d = generators.rocket(total_length=1000, body_diameter=100, fin_count=4)
    kinds = [f.kind for f in d.features]
    _check("cone" in kinds, "has nose cone")
    _check("polar_array" in kinds, "has fins array")
    _check(d.total_volume() > 0, "positive volume")


def test_build_from_text_endtoend():
    d = parser.build_from_text("design a 3 m rocket with 8 fins")
    _check(d.name == "Rocket", "name")
    fins = [f for f in d.features if f.kind == "polar_array"][0]
    _check(fins.count == 8, f"fin count {fins.count}")


def test_all_generators_produce_volume():
    for name, fn in generators.REGISTRY.items():
        d = fn()
        _check(d.total_volume() > 0, f"{name} volume must be > 0")


def test_specific_domain_beats_generic():
    # "GPU heatsink" must resolve to gpu, not the generic heatsink
    _check(parser.detect_domain("a GPU heatsink with 24 fins") == "gpu", "gpu>heatsink")
    _check(parser.detect_domain("a CPU cooler") == "cpu", "cpu>cooler")


def test_car_word_boundary():
    # "car" must NOT fire inside "graphics card"
    _check(parser.detect_domain("a graphics card cooler") == "gpu", "card!=car")


def test_rocket_no_negative_volume():
    # regression: a bare "2 metre rocket" once set diameter == length,
    # producing a negative body length / volume.
    d = parser.build_from_text("design a 2 metre rocket with 6 fins")
    for f in d.features:
        _check(f.volume() >= 0, f"{f.name} volume must be >= 0, got {f.volume()}")
    _check(d.meta.get("prompt"), "prompt stored in meta")


def test_cone_volume_formula():
    c = Cone(radius1=2, radius2=0, height=3)  # cone: pi*r^2*h/3
    import math
    _check(abs(c.volume() - math.pi * 4 * 3 / 3) < 1e-9, "cone vol")


def run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} tests passed.")


if __name__ == "__main__":
    run()
