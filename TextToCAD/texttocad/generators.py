"""
Parametric domain generators.

Each generator returns a ``Design`` built from the pure-Python spec model.
They encode just enough engineering geometry to produce a recognisable,
dimensionally-sensible starting point that the user can then refine in
FreeCAD. These are *templates*, not certified engineering models.
"""

from __future__ import annotations

import math

from . import spec
from .spec import (
    Box, Boolean, Cone, Cylinder, Design, Extrude, LinearArray, Placement,
    PolarArray, Solid, Sphere, Torus,
)


# --------------------------------------------------------------------------- #
# Rocket
# --------------------------------------------------------------------------- #
def rocket(total_length: float = 1000.0, body_diameter: float = 100.0,
           fin_count: int = 4, stages: int = 1) -> Design:
    d = Design(name="Rocket", meta={"domain": "rocket"})
    r = body_diameter / 2.0
    nose_len = body_diameter * 2.5
    body_len = total_length - nose_len
    fin_root_chord = body_diameter * 1.2
    fin_semispan = body_diameter * 0.9
    d.meta["params"] = dict(
        total_length=total_length, body_diameter=body_diameter,
        fin_count=fin_count, stages=stages, nose_len=nose_len,
        body_len=body_len, fin_root_chord=fin_root_chord,
        fin_semispan=fin_semispan, nose_shape="cone",
    )

    # Nose cone (ogive approximated by a tangent cone)
    d.add(Cone(name="NoseCone", radius1=r, radius2=0.0, height=nose_len,
               placement=Placement(pos=(0, 0, body_len))))

    # Body tube (optionally split into stages)
    stage_len = body_len / max(stages, 1)
    for s in range(stages):
        d.add(Cylinder(name=f"Stage{s+1}Body", radius=r, height=stage_len,
                       placement=Placement(pos=(0, 0, s * stage_len))))

    # Fins arranged radially at the base
    fin = Box(name="Fin", length=body_diameter * 0.9, width=r * 0.08,
              height=body_diameter * 1.2,
              placement=Placement(pos=(r, 0, 0)))
    d.add(PolarArray(name="Fins", base=fin, count=fin_count, radius=r))

    # Nozzle bell at the tail
    d.add(Cone(name="Nozzle", radius1=r * 0.35, radius2=r * 0.7,
               height=body_diameter * 0.8,
               placement=Placement(pos=(0, 0, -body_diameter * 0.8))))
    return d


# --------------------------------------------------------------------------- #
# Jet / turbofan engine (schematic)
# --------------------------------------------------------------------------- #
def jet_engine(length: float = 3000.0, fan_diameter: float = 1200.0,
               blade_count: int = 24) -> Design:
    d = Design(name="JetEngine", meta={"domain": "jet"})
    d.meta["params"] = dict(length=length, fan_diameter=fan_diameter,
                            blade_count=blade_count)
    rfan = fan_diameter / 2.0
    rcore = rfan * 0.45

    # Nacelle (outer cowling) as a thick tube == outer cut by inner
    outer = Cylinder(radius=rfan * 1.08, height=length)
    inner = Cylinder(radius=rfan, height=length,
                     placement=Placement(pos=(0, 0, 0)))
    d.add(Boolean(name="Nacelle", op="cut", children=[outer, inner]))

    # Spinner (nose cone)
    d.add(Cone(name="Spinner", radius1=rcore * 0.6, radius2=0.0,
               height=fan_diameter * 0.4,
               placement=Placement(pos=(0, 0, 0))))

    # Fan blades
    blade = Box(name="FanBlade", length=(rfan - rcore) * 0.95,
                width=fan_diameter * 0.04, height=fan_diameter * 0.18,
                placement=Placement(pos=(rcore, 0, fan_diameter * 0.1)))
    d.add(PolarArray(name="FanStage", base=blade, count=blade_count,
                     radius=rcore))

    # Core (compressor/turbine spool)
    d.add(Cylinder(name="Core", radius=rcore, height=length * 0.8,
                   placement=Placement(pos=(0, 0, fan_diameter * 0.2))))

    # Exhaust cone
    d.add(Cone(name="ExhaustPlug", radius1=rcore * 0.8, radius2=rcore * 0.2,
               height=fan_diameter * 0.5,
               placement=Placement(pos=(0, 0, length))))
    return d


# --------------------------------------------------------------------------- #
# CPU / GPU heatsink (the mechanical, CAD-able part of a "chip")
# --------------------------------------------------------------------------- #
def heatsink(base: float = 40.0, fin_count: int = 16, fin_height: float = 30.0,
             with_die: bool = True, label: str = "CPU") -> Design:
    d = Design(name=f"{label}Heatsink", meta={"domain": "electronics-thermal"})
    d.meta["params"] = dict(base=base, fin_count=fin_count, fin_height=fin_height,
                            label=label, default_power=250.0 if label == "GPU" else 95.0)
    base_thk = 4.0

    # Cold plate / base
    d.add(Box(name="BasePlate", length=base, width=base, height=base_thk))

    # Fin stack
    fin_thk = base * 0.6 / fin_count
    pitch = base / fin_count
    fin = Box(name="Fin", length=fin_thk, width=base, height=fin_height,
              placement=Placement(pos=(0, 0, base_thk)))
    d.add(LinearArray(name="FinStack", base=fin, count=fin_count,
                      spacing=(pitch, 0, 0)))

    # Silicon die + package substrate underneath (the "chip")
    if with_die:
        die = base * 0.45
        d.add(Box(name="PackageSubstrate", length=base * 0.95,
                  width=base * 0.95, height=2.0,
                  placement=Placement(pos=(0, 0, -2.0))))
        d.add(Box(name="SiliconDie", length=die, width=die, height=0.8,
                  placement=Placement(pos=(base * 0.275, base * 0.275, -0.8))))
    return d


def cpu(**kw) -> Design:
    kw.setdefault("label", "CPU")
    return heatsink(**kw)


def gpu(**kw) -> Design:
    # GPUs run hotter & bigger -> larger base + more fins by default
    kw.setdefault("label", "GPU")
    kw.setdefault("base", 55.0)
    kw.setdefault("fin_count", 24)
    kw.setdefault("fin_height", 40.0)
    return heatsink(**kw)


# --------------------------------------------------------------------------- #
# Car body (massing model)
# --------------------------------------------------------------------------- #
def car(length: float = 4500.0, width: float = 1850.0, height: float = 1450.0,
        wheel_radius: float = 320.0) -> Design:
    d = Design(name="Car", meta={"domain": "automotive"})
    d.meta["params"] = dict(length=length, width=width, height=height,
                            wheel_radius=wheel_radius)
    body_h = height * 0.55
    cabin_h = height - body_h

    # Lower body
    d.add(Box(name="LowerBody", length=length, width=width, height=body_h,
              placement=Placement(pos=(0, 0, wheel_radius))))

    # Greenhouse / cabin (set back, narrower)
    d.add(Box(name="Cabin", length=length * 0.45, width=width * 0.9,
              height=cabin_h,
              placement=Placement(pos=(length * 0.28, width * 0.05,
                                       wheel_radius + body_h))))

    # Four wheels (cylinders laid on their side)
    wheel = Cylinder(name="Wheel", radius=wheel_radius, height=width * 0.12,
                     placement=Placement(pos=(0, 0, 0), axis=(1, 0, 0),
                                         angle=90.0))
    offsets = [
        (length * 0.18, 0, wheel_radius),
        (length * 0.18, width, wheel_radius),
        (length * 0.82, 0, wheel_radius),
        (length * 0.82, width, wheel_radius),
    ]
    for i, off in enumerate(offsets):
        import copy
        w = copy.deepcopy(wheel)
        w.name = f"Wheel{i+1}"
        w.placement.pos = off
        d.add(w)
    return d


# --------------------------------------------------------------------------- #
# Spur gear
# --------------------------------------------------------------------------- #
def gear(teeth: int = 20, module: float = 2.0, thickness: float = 8.0,
         bore: float = 6.0) -> Design:
    d = Design(name="Gear", meta={"domain": "mechanical"})
    d.meta["params"] = dict(teeth=teeth, module=module, thickness=thickness,
                            bore=bore)
    pitch_r = module * teeth / 2.0
    tooth = Box(name="Tooth", length=module * 1.2, width=module * 1.6,
                height=thickness,
                placement=Placement(pos=(pitch_r - module * 0.6,
                                         -module * 0.8, 0)))
    body = Boolean(op="union", children=[
        Cylinder(name="Hub", radius=pitch_r, height=thickness),
        PolarArray(name="Teeth", base=tooth, count=teeth, radius=pitch_r),
    ])
    d.add(Boolean(name="Gear", op="cut", children=[
        body, Cylinder(name="Bore", radius=bore / 2.0, height=thickness)]))
    return d


# --------------------------------------------------------------------------- #
# Propeller
# --------------------------------------------------------------------------- #
def propeller(blade_count: int = 3, diameter: float = 300.0,
              hub_diameter: float = 40.0) -> Design:
    d = Design(name="Propeller", meta={"domain": "aerospace"})
    rhub = hub_diameter / 2.0
    d.add(Cylinder(name="Hub", radius=rhub, height=hub_diameter * 0.6))
    blade = Box(name="Blade", length=diameter / 2.0 - rhub,
                width=diameter * 0.06, height=hub_diameter * 0.25,
                placement=Placement(pos=(rhub, 0, hub_diameter * 0.18),
                                    axis=(1, 0, 0), angle=18.0))
    d.add(PolarArray(name="Blades", base=blade, count=blade_count, radius=rhub))
    return d


# --------------------------------------------------------------------------- #
# Bolt (hex-head massing)
# --------------------------------------------------------------------------- #
def bolt(diameter: float = 10.0, length: float = 40.0) -> Design:
    d = Design(name="Bolt", meta={"domain": "fastener"})
    head_h = diameter * 0.7
    d.add(Cylinder(name="Head", radius=diameter * 0.9, height=head_h,
                   placement=Placement(pos=(0, 0, length))))
    d.add(Cylinder(name="Shank", radius=diameter / 2.0, height=length))
    return d


# --------------------------------------------------------------------------- #
# L-bracket
# --------------------------------------------------------------------------- #
def bracket(length: float = 80.0, width: float = 60.0, height: float = 80.0,
            thickness: float = 6.0) -> Design:
    d = Design(name="Bracket", meta={"domain": "mechanical"})
    d.add(Box(name="Base", length=length, width=width, height=thickness))
    d.add(Box(name="Wall", length=thickness, width=width, height=height))
    return d


# --------------------------------------------------------------------------- #
# Bolt-circle flange
# --------------------------------------------------------------------------- #
def flange(diameter: float = 120.0, bore: float = 50.0, thickness: float = 10.0,
           bolt_count: int = 6, bolt_hole: float = 10.0) -> Design:
    d = Design(name="Flange", meta={"domain": "mechanical"})
    R = diameter / 2.0
    bolt_circle = (R + bore / 2.0) / 2.0
    hole = Cylinder(name="BoltHole", radius=bolt_hole / 2.0, height=thickness,
                    placement=Placement(pos=(bolt_circle, 0, 0)))
    d.add(Boolean(name="Flange", op="cut", children=[
        Cylinder(name="Disc", radius=R, height=thickness),
        Cylinder(name="Bore", radius=bore / 2.0, height=thickness),
        PolarArray(name="BoltHoles", base=hole, count=bolt_count,
                   radius=bolt_circle),
    ]))
    return d


# --------------------------------------------------------------------------- #
# Enclosure / case (hollow shell)
# --------------------------------------------------------------------------- #
def enclosure(length: float = 120.0, width: float = 80.0, height: float = 40.0,
              wall: float = 2.5) -> Design:
    d = Design(name="Enclosure", meta={"domain": "electronics"})
    outer = Box(name="Outer", length=length, width=width, height=height)
    inner = Box(name="Cavity", length=length - 2 * wall, width=width - 2 * wall,
                height=height, placement=Placement(pos=(wall, wall, wall)))
    d.add(Boolean(name="Shell", op="cut", children=[outer, inner]))
    return d


# --------------------------------------------------------------------------- #
# NACA 4-digit airfoil wing
# --------------------------------------------------------------------------- #
def naca4_profile(code: str = "2412", chord: float = 200.0, n: int = 40):
    """Return a closed list of (x, y) points for a NACA 4-digit airfoil."""
    m = int(code[0]) / 100.0          # max camber
    p = int(code[1]) / 10.0           # camber position
    t = int(code[2:]) / 100.0         # thickness
    upper, lower = [], []
    for i in range(n + 1):
        beta = math.pi * i / n
        x = (1 - math.cos(beta)) / 2.0    # cosine spacing
        yt = 5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x * x
                      + 0.2843 * x ** 3 - 0.1015 * x ** 4)
        if p > 0 and 0 < x < 1:
            if x < p:
                yc = m / (p * p) * (2 * p * x - x * x)
                dyc = 2 * m / (p * p) * (p - x)
            else:
                yc = m / ((1 - p) ** 2) * ((1 - 2 * p) + 2 * p * x - x * x)
                dyc = 2 * m / ((1 - p) ** 2) * (p - x)
        else:
            yc, dyc = 0.0, 0.0
        th = math.atan(dyc)
        upper.append(((x - yt * math.sin(th)) * chord,
                      (yc + yt * math.cos(th)) * chord))
        lower.append(((x + yt * math.sin(th)) * chord,
                      (yc - yt * math.cos(th)) * chord))
    # closed loop: upper LE->TE then lower TE->LE
    return upper + lower[::-1][1:-1]


def wing(span: float = 1000.0, chord: float = 200.0, airfoil: str = "2412") -> Design:
    d = Design(name="Wing", meta={"domain": "aerospace"})
    d.meta["params"] = dict(span=span, chord=chord, airfoil=airfoil)
    prof = naca4_profile(airfoil, chord=chord)
    # extrude along Z (span), then it's a constant-section wing
    d.add(Extrude(name="WingBox", profile=prof, height=span))
    return d


# --------------------------------------------------------------------------- #
# I-beam (structural section, extruded profile)
# --------------------------------------------------------------------------- #
def ibeam(length: float = 1000.0, height: float = 200.0, width: float = 100.0,
          web: float = 8.0, flange: float = 12.0) -> Design:
    d = Design(name="IBeam", meta={"domain": "structural"})
    d.meta["params"] = dict(length=length, height=height, width=width,
                            web=web, flange=flange)
    hw, hh = width / 2.0, height / 2.0
    tw = web / 2.0
    # I-section profile (CCW), centred on origin
    prof = [
        (-hw, -hh), (hw, -hh), (hw, -hh + flange), (tw, -hh + flange),
        (tw, hh - flange), (hw, hh - flange), (hw, hh), (-hw, hh),
        (-hw, hh - flange), (-tw, hh - flange), (-tw, -hh + flange),
        (-hw, -hh + flange),
    ]
    d.add(Extrude(name="Section", profile=prof, height=length))
    return d


# --------------------------------------------------------------------------- #
# Pipe / tube (hollow cylinder)
# --------------------------------------------------------------------------- #
def pipe(length: float = 500.0, outer_diameter: float = 60.0,
         wall: float = 4.0) -> Design:
    d = Design(name="Pipe", meta={"domain": "mechanical"})
    d.meta["params"] = dict(length=length, outer_diameter=outer_diameter, wall=wall)
    ro = outer_diameter / 2.0
    d.add(Boolean(name="Pipe", op="cut", children=[
        Cylinder(name="Outer", radius=ro, height=length),
        Cylinder(name="Bore", radius=ro - wall, height=length)]))
    return d


# --------------------------------------------------------------------------- #
# Registry used by the parser
# --------------------------------------------------------------------------- #
REGISTRY = {
    "rocket": rocket,
    "jet": jet_engine,
    "jet_engine": jet_engine,
    "engine": jet_engine,
    "cpu": cpu,
    "gpu": gpu,
    "heatsink": heatsink,
    "car": car,
    "gear": gear,
    "propeller": propeller,
    "bolt": bolt,
    "bracket": bracket,
    "flange": flange,
    "enclosure": enclosure,
    "wing": wing,
    "ibeam": ibeam,
    "pipe": pipe,
}
