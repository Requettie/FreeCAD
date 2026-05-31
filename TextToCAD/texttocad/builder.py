"""
Spec -> FreeCAD geometry.

This is the only module that imports FreeCAD. It walks a ``Design`` tree and
emits real ``Part`` solids into the active document. Import is guarded so the
rest of the package (spec/parser/generators) stays testable without FreeCAD.
"""

from __future__ import annotations

import math

from . import spec

try:
    import FreeCAD as App
    import Part
    _HAS_FREECAD = True
except Exception:  # pragma: no cover - only true inside FreeCAD
    _HAS_FREECAD = False


def _placement(p: "spec.Placement"):
    return App.Placement(
        App.Vector(*p.pos),
        App.Rotation(App.Vector(*p.axis), p.angle),
    )


def _shape(node: "spec.Solid"):
    """Return a Part.Shape for a single spec node (recursive)."""
    k = node.kind
    if k == "box":
        s = Part.makeBox(node.length, node.width, node.height)
    elif k == "cylinder":
        s = Part.makeCylinder(node.radius, node.height)
    elif k == "cone":
        s = Part.makeCone(node.radius1, node.radius2, node.height)
    elif k == "sphere":
        s = Part.makeSphere(node.radius)
    elif k == "torus":
        s = Part.makeTorus(node.radius1, node.radius2)
    elif k == "boolean":
        shapes = [_shape(c) for c in node.children]
        s = shapes[0]
        for nxt in shapes[1:]:
            if node.op == "cut":
                s = s.cut(nxt)
            elif node.op == "common":
                s = s.common(nxt)
            else:
                s = s.fuse(nxt)
    elif k == "polar_array":
        base = _shape(node.base)
        copies = []
        for i in range(node.count):
            ang = 360.0 / node.count * i
            pl = App.Placement(App.Vector(0, 0, 0),
                               App.Rotation(App.Vector(0, 0, 1), ang))
            copies.append(base.transformGeometry(pl.toMatrix()))
        s = copies[0]
        for c in copies[1:]:
            s = s.fuse(c)
    elif k == "linear_array":
        base = _shape(node.base)
        dx, dy, dz = node.spacing
        copies = []
        for i in range(node.count):
            pl = App.Placement(App.Vector(dx * i, dy * i, dz * i),
                               App.Rotation())
            copies.append(base.transformGeometry(pl.toMatrix()))
        s = copies[0]
        for c in copies[1:]:
            s = s.fuse(c)
    else:
        raise ValueError(f"Unknown spec kind: {k}")

    s = s.transformGeometry(_placement(node.placement).toMatrix())
    return s


def build(design: "spec.Design", doc=None):
    """Materialise a Design into a FreeCAD document. Returns the document."""
    if not _HAS_FREECAD:
        raise RuntimeError(
            "FreeCAD is not available. Run this inside FreeCAD's Python "
            "console or the FreeCAD GUI."
        )
    if doc is None:
        doc = App.newDocument(design.name)
    for node in design.features:
        obj = doc.addObject("Part::Feature", node.name or node.kind)
        obj.Shape = _shape(node)
    doc.recompute()
    try:
        import FreeCADGui as Gui
        Gui.SendMsgToActiveView("ViewFit")
    except Exception:
        pass
    return doc
