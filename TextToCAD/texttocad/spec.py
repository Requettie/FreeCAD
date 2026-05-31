"""
Portable design-spec model for Text-to-CAD.

This module is *pure Python* (no FreeCAD import) so it can be unit-tested
outside the FreeCAD environment. A ``Design`` is a tree of parametric
``Feature`` nodes. The ``builder`` module turns a ``Design`` into real
FreeCAD ``Part`` geometry; the spec itself stays engine-agnostic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

Vec = Tuple[float, float, float]


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #
@dataclass
class Placement:
    """Position + axis-angle rotation, in millimetres / degrees."""
    pos: Vec = (0.0, 0.0, 0.0)
    axis: Vec = (0.0, 0.0, 1.0)
    angle: float = 0.0


@dataclass
class Solid:
    """Base parametric solid. Subclasses set ``kind`` and dimension fields."""
    kind: str = "solid"
    placement: Placement = field(default_factory=Placement)
    name: str = ""

    def volume(self) -> float:
        raise NotImplementedError


@dataclass
class Box(Solid):
    length: float = 1.0
    width: float = 1.0
    height: float = 1.0
    kind: str = "box"

    def volume(self) -> float:
        return self.length * self.width * self.height


@dataclass
class Cylinder(Solid):
    radius: float = 1.0
    height: float = 1.0
    kind: str = "cylinder"

    def volume(self) -> float:
        return math.pi * self.radius ** 2 * self.height


@dataclass
class Cone(Solid):
    radius1: float = 1.0
    radius2: float = 0.0
    height: float = 1.0
    kind: str = "cone"

    def volume(self) -> float:
        r1, r2, h = self.radius1, self.radius2, self.height
        return math.pi * h / 3.0 * (r1 * r1 + r1 * r2 + r2 * r2)


@dataclass
class Sphere(Solid):
    radius: float = 1.0
    kind: str = "sphere"

    def volume(self) -> float:
        return 4.0 / 3.0 * math.pi * self.radius ** 3


@dataclass
class Torus(Solid):
    radius1: float = 2.0  # ring radius
    radius2: float = 0.5  # tube radius
    kind: str = "torus"

    def volume(self) -> float:
        return 2.0 * math.pi ** 2 * self.radius1 * self.radius2 ** 2


# --------------------------------------------------------------------------- #
# Combinators
# --------------------------------------------------------------------------- #
@dataclass
class Boolean(Solid):
    op: str = "union"            # union | cut | common
    children: List[Solid] = field(default_factory=list)
    kind: str = "boolean"

    def volume(self) -> float:
        if not self.children:
            return 0.0
        if self.op == "union":
            return sum(c.volume() for c in self.children)
        # cut/common: best-effort estimate (real value comes from the kernel)
        return self.children[0].volume()


@dataclass
class PolarArray(Solid):
    """Revolve copies of ``base`` around the Z axis."""
    base: Optional[Solid] = None
    count: int = 4
    radius: float = 10.0
    kind: str = "polar_array"

    def volume(self) -> float:
        return (self.base.volume() * self.count) if self.base else 0.0


@dataclass
class LinearArray(Solid):
    base: Optional[Solid] = None
    count: int = 2
    spacing: Vec = (10.0, 0.0, 0.0)
    kind: str = "linear_array"

    def volume(self) -> float:
        return (self.base.volume() * self.count) if self.base else 0.0


# --------------------------------------------------------------------------- #
# Top-level design
# --------------------------------------------------------------------------- #
@dataclass
class Design:
    name: str = "Design"
    features: List[Solid] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def add(self, solid: Solid) -> Solid:
        self.features.append(solid)
        return solid

    def total_volume(self) -> float:
        return sum(f.volume() for f in self.features)

    def summary(self) -> str:
        lines = [f"Design '{self.name}' — {len(self.features)} top-level feature(s)"]
        for f in self.features:
            lines.append(f"  - {f.name or f.kind} ({f.kind}), vol~={f.volume():.1f} mm^3")
        return "\n".join(lines)
