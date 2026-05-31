"""
Engineering-grade analysis (NOT certification).

Every metric here is computed from a published, named formula and reported with
its source. These are first-order analytical estimates with explicit
assumptions -- useful for sizing and sanity-checking. They are **not** a
substitute for FEA/CFD, physical test, or a licensed PE's stamp, and nothing
here certifies a design as flight-, road-, or pressure-worthy.

Primary references:
  - Barrowman, J. (1967), "The Practical Calculation of the Aerodynamic
    Characteristics of Slender Finned Vehicles", NASA.
  - Tsiolkovsky rocket equation (ideal Delta-v).
  - Incropera & DeWitt, "Fundamentals of Heat and Mass Transfer" (fin theory).
  - Hucho, "Aerodynamics of Road Vehicles" (drag).
  - AGMA 2001 / Lewis bending equation (gear tooth stress).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from . import spec

G0 = 9.80665          # m/s^2
RHO_AIR = 1.225       # kg/m^3 at sea level, 15 C
MU_AIR = 1.81e-5      # Pa*s

# Material density (kg/m^3) and thermal conductivity k (W/m.K)
MATERIALS = {
    "aluminium": (2700.0, 205.0),
    "aluminum": (2700.0, 205.0),
    "steel": (7850.0, 50.0),
    "stainless": (8000.0, 16.0),
    "titanium": (4500.0, 22.0),
    "copper": (8960.0, 401.0),
    "abs": (1040.0, 0.17),
    "cfrp": (1600.0, 7.0),
}


@dataclass
class Metric:
    name: str
    value: float
    unit: str
    note: str = ""          # formula / citation / assumption

    def line(self) -> str:
        v = f"{self.value:,.3g}" if abs(self.value) >= 1 else f"{self.value:.3g}"
        s = f"  {self.name:<28} {v:>12} {self.unit}"
        return s + (f"   [{self.note}]" if self.note else "")


@dataclass
class Report:
    title: str
    metrics: List[Metric] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add(self, *a, **k):
        self.metrics.append(Metric(*a, **k))

    def text(self) -> str:
        out = [f"== {self.title} ==",
               "(engineering-grade estimate, NOT certified)"]
        out += [m.line() for m in self.metrics]
        if self.warnings:
            out.append("  warnings:")
            out += [f"    ! {w}" for w in self.warnings]
        return "\n".join(out)


# --------------------------------------------------------------------------- #
# Generic mass properties (work for any Design)
# --------------------------------------------------------------------------- #
def surface_area_mm2(design: "spec.Design", seg: int = 48) -> float:
    from . import mesh
    tris = mesh.mesh_design(design, seg=seg)
    total = 0.0
    for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in tris:
        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = cx - ax, cy - ay, cz - az
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        total += 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)
    return total


def mass_properties(design: "spec.Design", material: str = "aluminium",
                    report: Optional[Report] = None) -> Report:
    rep = report or Report(f"{design.name} mass properties")
    density, _ = MATERIALS.get(material.lower(), MATERIALS["aluminium"])
    from . import mesh
    vol_mm3 = design.total_volume()             # hollow-aware spec volume
    vol_m3 = vol_mm3 * 1e-9
    rep.add("material volume", vol_mm3, "mm^3",
            "spec volume; cuts subtract (assumes contained)")
    rep.add("mesh hull volume", mesh.mesh_volume(design), "mm^3",
            "tessellated outer hull (cuts not subtracted)")
    rep.add("mass", vol_m3 * density, "kg",
            f"material vol x rho ({material}, {density:.0f} kg/m^3); solid walls")
    rep.add("surface area", surface_area_mm2(design) / 100.0, "cm^2", "mesh sum")
    return rep


# --------------------------------------------------------------------------- #
# Rocket: Barrowman stability + ideal Delta-v
# --------------------------------------------------------------------------- #
def analyze_rocket(p: dict, isp: float = 250.0, prop_mass_fraction: float = 0.8,
                   material: str = "aluminium") -> Report:
    rep = Report("Rocket aerodynamic & performance estimate")
    d = p["body_diameter"]
    R = d / 2.0
    Ln = p["nose_len"]
    L = p["total_length"]
    N = p["fin_count"]
    cr = p["fin_root_chord"]          # rectangular fins: root = tip chord
    s = p["fin_semispan"]

    fineness = L / d
    rep.add("fineness ratio L/d", fineness, "-", "slender-body; aim 10-20")
    rep.add("reference area", math.pi * R ** 2, "mm^2", "pi*d^2/4")

    # --- Barrowman normal-force coefficients & CP (from nose tip, +down) ---
    # Nose (cone): CNa = 2, Xn = 0.666*Ln
    CNa_n, Xn = 2.0, 0.666 * Ln
    # Fins (N rectangular fins)
    lf = s                                       # mid-chord span (no sweep)
    Kfb = 1.0 + R / (s + R)                       # body-interference factor
    CNa_f = Kfb * (4 * N * (s / d) ** 2) / (1 + math.sqrt(1 + (2 * lf / (cr + cr)) ** 2))
    # Fin LE is at the base; tip = nose, so distance from tip to fin LE:
    Xfin_LE = (L - cr)                            # fins flush to tail
    Xf = Xfin_LE + cr / 4.0                        # rect-fin CP at quarter chord
    CNa = CNa_n + CNa_f
    Xcp = (CNa_n * Xn + CNa_f * Xf) / CNa          # from nose tip

    # --- CG from volume-weighted centroids of the solid features (from tip) ---
    z_tip = p["body_len"] + Ln
    moms, vols = 0.0, 0.0
    for f in _rocket_centroids(p):
        z_from_tip = z_tip - f[0]
        moms += f[1] * z_from_tip
        vols += f[1]
    Xcg = moms / vols if vols else L / 2.0

    static_margin = (Xcp - Xcg) / d
    rep.add("CNa (total)", CNa, "1/rad", "Barrowman")
    rep.add("CP from nose", Xcp, "mm", "Barrowman")
    rep.add("CG from nose", Xcg, "mm", "volume-weighted, uniform density")
    rep.add("static margin", static_margin, "cal", "(CP-CG)/d; stable 1-2")
    if static_margin < 1.0:
        rep.warnings.append(f"static margin {static_margin:.2f} cal < 1: likely UNSTABLE")
    elif static_margin > 2.5:
        rep.warnings.append(f"static margin {static_margin:.2f} cal > 2.5: over-stable")

    # --- Ideal Delta-v (Tsiolkovsky) ---
    mass_ratio = 1.0 / (1.0 - prop_mass_fraction)
    dv = isp * G0 * math.log(mass_ratio)
    rep.add("ideal Delta-v", dv, "m/s",
            f"Tsiolkovsky; Isp={isp:.0f}s, prop frac={prop_mass_fraction:.2f}")
    return rep


def _rocket_centroids(p: dict):
    """(centroid_z_in_up_coords, volume) for each major rocket solid."""
    import math as _m
    r = p["body_diameter"] / 2.0
    out = []
    # nose cone: base at body_len, apex up; solid-cone centroid h/4 above base
    nose_v = _m.pi * r ** 2 * p["nose_len"] / 3.0
    out.append((p["body_len"] + p["nose_len"] / 4.0, nose_v))
    # body (single equivalent cylinder over body_len)
    body_v = _m.pi * r ** 2 * p["body_len"]
    out.append((p["body_len"] / 2.0, body_v))
    return out


# --------------------------------------------------------------------------- #
# Heatsink: fin theory + thermal resistance
# --------------------------------------------------------------------------- #
def analyze_heatsink(p: dict, power_w: float = 95.0, t_ambient: float = 25.0,
                     forced: bool = True, material: str = "aluminium") -> Report:
    rep = Report("Heatsink thermal estimate")
    base = p["base"] / 1000.0                      # m
    n = p["fin_count"]
    fh = p["fin_height"] / 1000.0
    _, k = MATERIALS.get(material.lower(), MATERIALS["aluminium"])
    t_fin = (base * 0.6 / n)                        # matches generator geometry
    h = 50.0 if forced else 10.0                    # W/m^2.K convective coeff

    # fin efficiency eta = tanh(mL)/(mL), m = sqrt(2h/(k*t))
    m = math.sqrt(2 * h / (k * t_fin))
    eta = math.tanh(m * fh) / (m * fh)
    a_fin = 2 * base * fh * n                        # both faces of each fin
    a_base = base * base
    a_eff = eta * a_fin + a_base
    r_th = 1.0 / (h * a_eff)                         # K/W
    dT = power_w * r_th
    rep.add("convection coeff h", h, "W/m^2K", "forced" if forced else "natural")
    rep.add("fin efficiency", eta, "-", "tanh(mL)/mL, Incropera")
    rep.add("effective area", a_eff * 1e4, "cm^2", "eta*A_fin + A_base")
    rep.add("thermal resistance", r_th, "K/W", "1/(h*A_eff)")
    rep.add("temp rise dT", dT, "K", f"P*R_th, P={power_w:.0f} W")
    rep.add("junction temp", t_ambient + dT, "C", f"T_amb={t_ambient:.0f} C")
    if t_ambient + dT > 95:
        rep.warnings.append(f"junction {t_ambient+dT:.0f} C exceeds ~95 C: add airflow/area")
    return rep


# --------------------------------------------------------------------------- #
# Jet engine: fan tip Mach, disk loading, actuator-disk thrust
# --------------------------------------------------------------------------- #
def analyze_jet(p: dict, rpm: float = 3000.0, v_jet: float = 350.0,
                a_sound: float = 340.0) -> Report:
    rep = Report("Turbofan fan-stage estimate")
    rfan = p["fan_diameter"] / 2000.0                 # m
    blades = p["blade_count"]
    omega = 2 * math.pi * rpm / 60.0                  # rad/s
    v_tip = omega * rfan
    A = math.pi * rfan ** 2                            # fan disk area, m^2
    bpf = blades * rpm / 60.0                          # blade-passing freq, Hz

    rep.add("fan disk area", A, "m^2", "pi*r^2")
    rep.add("fan tip speed", v_tip, "m/s", f"omega*r, {rpm:.0f} rpm")
    rep.add("fan tip Mach", v_tip / a_sound, "-", "keep < ~1.2 (transonic)")
    rep.add("blade-pass freq", bpf, "Hz", "N*rpm/60 (acoustics)")

    # actuator-disk static thrust: F = rho*A*v_jet^2 (very rough)
    F = RHO_AIR * A * v_jet ** 2
    rep.add("static thrust (ideal)", F / 1000.0, "kN",
            f"rho*A*Vj^2, Vj={v_jet:.0f} m/s; actuator disk")
    if v_tip / a_sound > 1.2:
        rep.warnings.append(f"tip Mach {v_tip/a_sound:.2f} > 1.2: shock losses/noise")
    return rep


# --------------------------------------------------------------------------- #
# Car: aerodynamic drag & power
# --------------------------------------------------------------------------- #
def analyze_car(p: dict, cd: float = 0.30, speeds_kph=(100.0, 200.0)) -> Report:
    rep = Report("Vehicle aerodynamic estimate")
    A = (p["width"] / 1000.0) * (p["height"] / 1000.0)   # frontal area m^2
    rep.add("frontal area", A, "m^2", "w*h (bounding)")
    rep.add("drag area Cd*A", cd * A, "m^2", f"assumed Cd={cd:.2f}")
    for kph in speeds_kph:
        v = kph / 3.6
        Fd = 0.5 * RHO_AIR * cd * A * v * v
        rep.add(f"drag @ {kph:.0f} km/h", Fd, "N", "0.5*rho*Cd*A*v^2")
        rep.add(f"power @ {kph:.0f} km/h", Fd * v / 1000.0, "kW", "Fd*v")
    return rep


# --------------------------------------------------------------------------- #
# Gear: Lewis bending stress
# --------------------------------------------------------------------------- #
def analyze_gear(p: dict, torque_nm: float = 10.0) -> Report:
    rep = Report("Spur gear estimate")
    teeth = p["teeth"]
    module = p["module"]
    F = p["thickness"] / 1000.0                      # face width, m
    D = module * teeth / 1000.0                      # pitch dia, m
    Wt = torque_nm / (D / 2.0)                        # tangential load, N
    Y = 0.154 - 0.912 / teeth                         # Lewis form factor (20 deg)
    sigma = Wt / (F * (module / 1000.0) * Y)          # Pa
    rep.add("pitch diameter", D * 1000.0, "mm", "module*teeth")
    rep.add("tangential load", Wt, "N", f"T/(D/2), T={torque_nm:.0f} Nm")
    rep.add("Lewis factor Y", Y, "-", "20 deg full-depth")
    rep.add("bending stress", sigma / 1e6, "MPa", "Lewis: Wt/(F*m*Y)")
    if sigma / 1e6 > 200:
        rep.warnings.append(f"bending {sigma/1e6:.0f} MPa high for typical steel allowable")
    return rep


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #
def analyze(design: "spec.Design", **opts) -> Report:
    domain = design.meta.get("domain", "")
    params = design.meta.get("params", {})
    if domain == "rocket" and params:
        rep = analyze_rocket(params,
                             isp=opts.get("isp", 250.0),
                             prop_mass_fraction=opts.get("prop_mass_fraction", 0.8))
    elif domain == "electronics-thermal" and params:
        rep = analyze_heatsink(params,
                               power_w=opts.get("power_w", params.get("default_power", 95.0)),
                               forced=opts.get("forced", True))
    elif domain == "jet" and params:
        rep = analyze_jet(params, rpm=opts.get("rpm", 3000.0),
                          v_jet=opts.get("v_jet", 350.0))
    elif domain == "automotive" and params:
        rep = analyze_car(params, cd=opts.get("cd", 0.30))
    elif domain == "mechanical" and "teeth" in params:
        rep = analyze_gear(params, torque_nm=opts.get("torque_nm", 10.0))
    else:
        rep = Report(f"{design.name} (no domain-specific model)")
    mass_properties(design, opts.get("material", "aluminium"), rep)
    return rep
