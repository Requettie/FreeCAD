"""
Pure-Python tests — run WITHOUT FreeCAD:  python -m pytest TextToCAD/tests
(or plain `python TextToCAD/tests/test_core.py`).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from texttocad import parser, generators, spec  # noqa: E402
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


def test_new_domains_detected():
    cases = {
        "a 20 tooth gear": "gear",
        "a 3 blade propeller": "propeller",
        "an M10 bolt 40 mm long": "bolt",
        "an L-bracket": "bracket",
        "a 6 bolt flange": "flange",
        "a project enclosure": "enclosure",
    }
    for text, expected in cases.items():
        got = parser.detect_domain(text)
        _check(got == expected, f"{text!r} -> {got} (want {expected})")


def test_dimension_triple():
    dom, p = parser.parse("a project enclosure 120 x 80 x 40 mm")
    _check(dom == "enclosure", "enclosure")
    _check((p["length"], p["width"], p["height"]) == (120.0, 80.0, 40.0),
           f"triple mm {p}")
    # unit applies to all three; 'by' separator; cm conversion
    _, p2 = parser.parse("an enclosure 10 by 20 by 30 cm")
    _check((p2["length"], p2["width"], p2["height"]) == (100.0, 200.0, 300.0),
           f"triple cm {p2}")
    # comma-separated single dims must still work (no false triple)
    _, p3 = parser.parse("a 4.5 m long sedan, 1.85 m wide")
    _check(p3.get("length") == 4500.0 and p3.get("width") == 1850.0,
           f"car dims {p3}")


def test_gear_params_and_geometry():
    d = parser.build_from_text("a 24 tooth gear")
    g = d.features[0]
    _check(g.kind == "boolean" and g.op == "cut", "gear is a cut")
    teeth = [c for c in g.children[0].children if c.kind == "polar_array"][0]
    _check(teeth.count == 24, f"teeth {teeth.count}")


def test_flange_bolt_count():
    d = parser.build_from_text("a flange with 8 bolts")
    holes = [c for c in d.features[0].children if c.kind == "polar_array"][0]
    _check(holes.count == 8, f"bolt holes {holes.count}")


def test_stl_export_roundtrip(tmp="_t.stl"):
    import os
    from texttocad import mesh
    d = generators.gear()
    mesh.write_stl(d, tmp, seg=24)
    txt = open(tmp).read()
    n = txt.count("facet normal")
    _check(n > 0 and txt.startswith("solid"), "ascii stl")
    lo, hi, ntris = mesh.bounds(d, seg=24)
    _check(ntris == n, f"bounds tris {ntris} == facets {n}")
    os.remove(tmp)


def test_scad_booleans():
    from texttocad import export_scad
    s = export_scad.to_scad(generators.flange())
    _check("difference()" in s, "flange cut -> difference")
    s2 = export_scad.to_scad(generators.gear())
    _check("difference()" in s2 and "union()" in s2, "gear union+difference")


def test_all_registry_generators_mesh():
    from texttocad import mesh
    for name, fn in generators.REGISTRY.items():
        lo, hi, n = mesh.bounds(fn(), seg=12)
        _check(n > 0, f"{name} produced no triangles")
        for i in range(3):
            _check(hi[i] - lo[i] > 0, f"{name} zero extent on axis {i}")


def test_engineering_rocket_deltav():
    from texttocad import engineering as e
    import math
    rep = e.analyze_rocket(generators.rocket().meta["params"],
                           isp=300, prop_mass_fraction=0.9)
    dv = [m for m in rep.metrics if "Delta-v" in m.name][0]
    expected = 300 * e.G0 * math.log(1 / (1 - 0.9))
    _check(abs(dv.value - expected) < 1.0, f"dv {dv.value} vs {expected}")


def test_engineering_gear_lewis():
    from texttocad import engineering as e
    rep = e.analyze_gear({"teeth": 20, "module": 2.0, "thickness": 8.0,
                          "bore": 6.0}, torque_nm=10.0)
    sigma = [m for m in rep.metrics if "bending" in m.name][0]
    # Wt=500N, F=0.008, m=0.002, Y=0.108 -> ~289 MPa
    _check(280 < sigma.value < 300, f"gear stress {sigma.value} MPa")


def test_engineering_jet_tip_mach():
    from texttocad import engineering as e
    rep = e.analyze_jet({"fan_diameter": 1200, "blade_count": 24, "length": 3000},
                        rpm=3000.0)
    mach = [m for m in rep.metrics if "tip Mach" in m.name][0]
    # v_tip = (2*pi*3000/60)*0.6 = 188.5 m/s; /340 = 0.554
    _check(0.54 < mach.value < 0.57, f"tip Mach {mach.value}")
    bpf = [m for m in rep.metrics if "blade-pass" in m.name][0]
    _check(bpf.value == 1200.0, f"bpf {bpf.value}")


def test_engineering_car_drag():
    from texttocad import engineering as e
    rep = e.analyze_car({"length": 4500, "width": 1850, "height": 1450,
                         "wheel_radius": 320}, cd=0.30, speeds_kph=(100.0,))
    f = [m for m in rep.metrics if "drag @ 100" in m.name][0]
    # 0.5*1.225*0.30*(1.85*1.45)*(27.78^2) ~ 380 N
    _check(350 < f.value < 410, f"car drag {f.value} N")


def test_engineering_dispatch_and_disclaimer():
    from texttocad import engineering as e
    for fn in (generators.rocket, generators.gpu, generators.car,
               generators.gear, generators.jet_engine):
        txt = e.analyze(fn()).text()
        _check("NOT certified" in txt, "must carry non-certification disclaimer")
        _check("mass" in txt, "must report mass")


def test_extrude_and_mesh_volume():
    from texttocad import mesh
    sq = spec.Extrude(profile=[(0, 0), (10, 0), (10, 10), (0, 10)], height=10)
    _check(abs(sq.volume() - 1000.0) < 1e-6, "extrude spec volume")
    d = spec.Design(); d.add(sq)
    _check(abs(mesh.mesh_volume(d) - 1000.0) < 1e-6, "extrude mesh volume")
    b = spec.Design(); b.add(spec.Box(length=20, width=30, height=40))
    _check(abs(mesh.mesh_volume(b) - 24000.0) < 1e-6, "box mesh volume exact")


def test_ibeam_nonconvex_triangulation():
    from texttocad import mesh
    ib = generators.ibeam(length=1000, height=200, width=100, web=8, flange=12)
    spec_v = ib.features[0].volume()
    mesh_v = mesh.mesh_volume(ib)
    # robust ear-clipping must reproduce the exact prism volume
    _check(abs(mesh_v - spec_v) < 1.0, f"ibeam mesh {mesh_v} != spec {spec_v}")


def test_naca_wing():
    prof = generators.naca4_profile("2412", chord=200.0)
    _check(len(prof) > 20, "airfoil has points")
    ys = [y for _, y in prof]
    thickness = max(ys) - min(ys)
    _check(15 < thickness < 30, f"2412 thickness ~12% of 200 -> {thickness}")
    _, p = parser.parse("a NACA 2412 wing 1.5 m span")
    _check(p.get("airfoil") == "2412" and p.get("span") == 1500.0, f"wing parse {p}")


def test_pipe_is_hollow():
    import math
    d = generators.pipe(length=500, outer_diameter=60, wall=4)
    ro, ri = 30.0, 26.0
    expected = math.pi * (ro ** 2 - ri ** 2) * 500
    _check(abs(d.total_volume() - expected) < 1.0, f"pipe hollow vol {d.total_volume()}")


def test_new_breadth_domains_detected():
    for text, dom in {"a NACA wing": "wing", "an I-beam 3 m long": "ibeam",
                      "a steel pipe 60 mm diameter": "pipe"}.items():
        _check(parser.detect_domain(text) == dom, f"{text} -> {dom}")


def test_obj_export():
    import os
    from texttocad import mesh
    p = "_t.obj"
    mesh.write_obj(generators.gear(), p, seg=24)
    txt = open(p).read()
    nv = sum(1 for ln in txt.splitlines() if ln.startswith("v "))
    nf = sum(1 for ln in txt.splitlines() if ln.startswith("f "))
    ntris = len(mesh.mesh_design(generators.gear(), seg=24))
    _check(nf == ntris and nv > 0, f"obj faces {nf} vs tris {ntris}")
    os.remove(p)


def test_updater_parse_counts():
    from texttocad import updater
    _check(updater._parse_counts("0\t0") == (0, 0), "zero")
    _check(updater._parse_counts("2\t5") == (5, 2), "ahead2 behind5")
    _check(updater._parse_counts("garbage") is None, "bad input")


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
