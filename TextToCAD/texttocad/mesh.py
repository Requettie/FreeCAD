"""
Pure-Python tessellation + STL export.

Turns a ``Design`` (spec tree) into a triangle mesh and writes ASCII STL with
no external dependencies, so every prompt yields a viewable 3D file even
without FreeCAD or OpenSCAD installed.

Limitation: STL is a boundary mesh with no CSG engine. ``union`` and arrays
are exact (meshes are concatenated); ``cut``/``common`` are approximated by
meshing the first operand only. For exact booleans use the OpenSCAD or
FreeCAD path. This is documented and asserted in the tests.
"""

from __future__ import annotations

import math
import struct
from typing import List, Tuple

from . import spec

Vec = Tuple[float, float, float]
Tri = Tuple[Vec, Vec, Vec]
# A transform is (3x3 rotation as 3 rows, translation vec)
Xf = Tuple[Tuple[Vec, Vec, Vec], Vec]

_IDENT: Xf = (((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0, 0, 0))


# --------------------------------------------------------------------------- #
# Small linear-algebra helpers
# --------------------------------------------------------------------------- #
def _rot(axis: Vec, angle_deg: float):
    a = math.radians(angle_deg)
    x, y, z = axis
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    x, y, z = x / n, y / n, z / n
    c, s, t = math.cos(a), math.sin(a), 1 - math.cos(a)
    return (
        (t * x * x + c,     t * x * y - s * z, t * x * z + s * y),
        (t * x * y + s * z, t * y * y + c,     t * y * z - s * x),
        (t * x * z - s * y, t * y * z + s * x, t * z * z + c),
    )


def _matmul(A, B):
    return tuple(
        tuple(sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3))
        for i in range(3)
    )


def _apply(xf: Xf, p: Vec) -> Vec:
    (R, t) = xf
    return (
        R[0][0] * p[0] + R[0][1] * p[1] + R[0][2] * p[2] + t[0],
        R[1][0] * p[0] + R[1][1] * p[1] + R[1][2] * p[2] + t[1],
        R[2][0] * p[0] + R[2][1] * p[1] + R[2][2] * p[2] + t[2],
    )


def _compose(A: Xf, B: Xf) -> Xf:
    """Return transform that applies B then A:  (A o B)(p) = A(B(p))."""
    (Ra, ta), (Rb, tb) = A, B
    R = _matmul(Ra, Rb)
    t = (
        Ra[0][0] * tb[0] + Ra[0][1] * tb[1] + Ra[0][2] * tb[2] + ta[0],
        Ra[1][0] * tb[0] + Ra[1][1] * tb[1] + Ra[1][2] * tb[2] + ta[1],
        Ra[2][0] * tb[0] + Ra[2][1] * tb[1] + Ra[2][2] * tb[2] + ta[2],
    )
    return (R, t)


def _placement_xf(p: "spec.Placement") -> Xf:
    return (_rot(p.axis, p.angle), tuple(p.pos))


# --------------------------------------------------------------------------- #
# Primitive tessellators (local coordinates)
# --------------------------------------------------------------------------- #
def _quad(a, b, c, d) -> List[Tri]:
    return [(a, b, c), (a, c, d)]


def _box(l, w, h) -> List[Tri]:
    p = [(0, 0, 0), (l, 0, 0), (l, w, 0), (0, w, 0),
         (0, 0, h), (l, 0, h), (l, w, h), (0, w, h)]
    t = []
    t += _quad(p[0], p[3], p[2], p[1])  # bottom
    t += _quad(p[4], p[5], p[6], p[7])  # top
    t += _quad(p[0], p[1], p[5], p[4])  # front
    t += _quad(p[2], p[3], p[7], p[6])  # back
    t += _quad(p[1], p[2], p[6], p[5])  # right
    t += _quad(p[3], p[0], p[4], p[7])  # left
    return t


def _ring(r, z, seg):
    return [(r * math.cos(2 * math.pi * i / seg),
             r * math.sin(2 * math.pi * i / seg), z) for i in range(seg)]


def _cone(r1, r2, h, seg) -> List[Tri]:
    lo, hi = _ring(r1, 0, seg), _ring(r2, h, seg)
    t = []
    for i in range(seg):
        j = (i + 1) % seg
        t += _quad(lo[i], lo[j], hi[j], hi[i])  # side
    cb, ct = (0, 0, 0), (0, 0, h)
    for i in range(seg):
        j = (i + 1) % seg
        t.append((cb, lo[j], lo[i]))            # bottom cap
        if r2 > 1e-9:
            t.append((ct, hi[i], hi[j]))        # top cap
    return t


def _cylinder(r, h, seg) -> List[Tri]:
    return _cone(r, r, h, seg)


def _sphere(r, seg) -> List[Tri]:
    rings = max(seg // 2, 3)
    pts = []
    for i in range(rings + 1):
        lat = math.pi * i / rings - math.pi / 2
        row = [(r * math.cos(lat) * math.cos(2 * math.pi * j / seg),
                r * math.cos(lat) * math.sin(2 * math.pi * j / seg),
                r * math.sin(lat)) for j in range(seg)]
        pts.append(row)
    t = []
    for i in range(rings):
        for j in range(seg):
            k = (j + 1) % seg
            t += _quad(pts[i][j], pts[i][k], pts[i + 1][k], pts[i + 1][j])
    return t


def _poly_area2(poly) -> float:
    a, n = 0.0, len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def _point_in_tri(p, a, b, c) -> bool:
    (px, py), (ax, ay), (bx, by), (cx, cy) = p, a, b, c
    d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(d) < 1e-12:
        return False
    u = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
    v = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
    return u > 0 and v > 0 and (u + v) < 1


def _triangulate(poly) -> List[tuple]:
    """Ear-clipping triangulation of a simple polygon -> index triples."""
    n = len(poly)
    if n < 3:
        return []
    idx = list(range(n))
    if _poly_area2(poly) < 0:        # ensure CCW
        idx.reverse()
    tris, guard = [], 0
    while len(idx) > 3 and guard < 10 * n:
        guard += 1
        m = len(idx)
        for i in range(m):
            i0, i1, i2 = idx[(i - 1) % m], idx[i], idx[(i + 1) % m]
            a, b, c = poly[i0], poly[i1], poly[i2]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if cross <= 0:           # reflex/collinear -> not an ear
                continue
            if any(j not in (i0, i1, i2) and _point_in_tri(poly[j], a, b, c)
                   for j in idx):
                continue
            tris.append((i0, i1, i2))
            del idx[i]
            break
        else:
            break                    # no ear found (degenerate) -> stop
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def _extrude(profile, h) -> List[Tri]:
    poly = list(profile)
    cap = _triangulate(poly)
    tris: List[Tri] = []
    for a, b, c in cap:             # bottom (normal -Z): reversed winding
        tris.append(((poly[a][0], poly[a][1], 0), (poly[c][0], poly[c][1], 0),
                     (poly[b][0], poly[b][1], 0)))
    for a, b, c in cap:             # top (normal +Z)
        tris.append(((poly[a][0], poly[a][1], h), (poly[b][0], poly[b][1], h),
                     (poly[c][0], poly[c][1], h)))
    n = len(poly)
    for i in range(n):              # side walls
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        tris += _quad((x1, y1, 0), (x2, y2, 0), (x2, y2, h), (x1, y1, h))
    return tris


def _torus(r1, r2, seg) -> List[Tri]:
    major, minor = seg, max(seg // 2, 3)
    pts = []
    for i in range(major):
        u = 2 * math.pi * i / major
        row = []
        for j in range(minor):
            v = 2 * math.pi * j / minor
            row.append(((r1 + r2 * math.cos(v)) * math.cos(u),
                        (r1 + r2 * math.cos(v)) * math.sin(u),
                        r2 * math.sin(v)))
        pts.append(row)
    t = []
    for i in range(major):
        ii = (i + 1) % major
        for j in range(minor):
            jj = (j + 1) % minor
            t += _quad(pts[i][j], pts[ii][j], pts[ii][jj], pts[i][jj])
    return t


# --------------------------------------------------------------------------- #
# Recursive mesher
# --------------------------------------------------------------------------- #
def _mesh_node(node: "spec.Solid", xf: Xf, seg: int) -> List[Tri]:
    node_xf = _compose(xf, _placement_xf(node.placement))
    k = node.kind

    if k == "box":
        local = _box(node.length, node.width, node.height)
    elif k == "cylinder":
        local = _cylinder(node.radius, node.height, seg)
    elif k == "cone":
        local = _cone(node.radius1, node.radius2, node.height, seg)
    elif k == "sphere":
        local = _sphere(node.radius, seg)
    elif k == "torus":
        local = _torus(node.radius1, node.radius2, seg)
    elif k == "extrude":
        local = _extrude(node.profile, node.height)
    elif k == "boolean":
        if node.op == "union":
            out: List[Tri] = []
            for c in node.children:
                out += _mesh_node(c, node_xf, seg)
            return out
        # cut/common: approximate with first operand (documented limitation)
        return _mesh_node(node.children[0], node_xf, seg)
    elif k == "polar_array":
        out = []
        for i in range(node.count):
            idx = _compose(node_xf, (_rot((0, 0, 1), 360.0 / node.count * i),
                                     (0, 0, 0)))
            out += _mesh_node(node.base, idx, seg)
        return out
    elif k == "linear_array":
        out = []
        dx, dy, dz = node.spacing
        for i in range(node.count):
            idx = _compose(node_xf, (((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                                     (dx * i, dy * i, dz * i)))
            out += _mesh_node(node.base, idx, seg)
        return out
    else:
        raise ValueError(f"Unknown spec kind: {k}")

    return [tuple(_apply(node_xf, v) for v in tri) for tri in local]


def mesh_design(design: "spec.Design", seg: int = 48) -> List[Tri]:
    tris: List[Tri] = []
    for node in design.features:
        tris += _mesh_node(node, _IDENT, seg)
    return tris


# --------------------------------------------------------------------------- #
# STL writers
# --------------------------------------------------------------------------- #
def _normal(tri: Tri) -> Vec:
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    m = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return (nx / m, ny / m, nz / m)


def write_stl(design: "spec.Design", path: str, seg: int = 48,
              binary: bool = False) -> str:
    tris = mesh_design(design, seg=seg)
    if binary:
        with open(path, "wb") as f:
            f.write(b"Text-to-CAD binary STL".ljust(80, b"\0"))
            f.write(struct.pack("<I", len(tris)))
            for tri in tris:
                f.write(struct.pack("<3f", *_normal(tri)))
                for v in tri:
                    f.write(struct.pack("<3f", *v))
                f.write(struct.pack("<H", 0))
    else:
        name = design.name.replace(" ", "_")
        with open(path, "w", encoding="ascii") as f:
            f.write(f"solid {name}\n")
            for tri in tris:
                n = _normal(tri)
                f.write(f"  facet normal {n[0]:.6e} {n[1]:.6e} {n[2]:.6e}\n")
                f.write("    outer loop\n")
                for v in tri:
                    f.write(f"      vertex {v[0]:.6e} {v[1]:.6e} {v[2]:.6e}\n")
                f.write("    endloop\n  endfacet\n")
            f.write(f"endsolid {name}\n")
    return path


def mesh_volume(design: "spec.Design", seg: int = 48) -> float:
    """Signed-tetrahedra volume of the tessellated mesh (divergence theorem).

    More faithful to the actual geometry than summing spec primitives; for a
    closed mesh it equals the enclosed volume.
    """
    v = 0.0
    for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in mesh_design(design, seg=seg):
        v += (ax * (by * cz - bz * cy)
              - ay * (bx * cz - bz * cx)
              + az * (bx * cy - by * cx)) / 6.0
    return abs(v)


def bounds(design: "spec.Design", seg: int = 24):
    tris = mesh_design(design, seg=seg)
    pts = [v for tri in tris for v in tri]
    lo = tuple(min(p[i] for p in pts) for i in range(3))
    hi = tuple(max(p[i] for p in pts) for i in range(3))
    return lo, hi, len(tris)
