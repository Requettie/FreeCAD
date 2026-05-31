"""
Command-line interface:

    python -m texttocad "a 2 m rocket with 6 fins" -o rocket.stl
    python -m texttocad "a turbofan engine 3 m long" -o jet.scad
    python -m texttocad "a 20-tooth gear" --print     # just describe

Format is inferred from the output extension (.stl / .scad), or set with -f.
Runs fully offline; pass --llm to use Claude when ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations

import argparse
import os
import sys

from . import parser as _parser


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="texttocad",
                                 description="Generate CAD from a text prompt.")
    ap.add_argument("prompt", help="natural-language description of the part")
    ap.add_argument("-o", "--output", help="output file (.stl or .scad)")
    ap.add_argument("-f", "--format", choices=["stl", "scad"],
                    help="force output format (else inferred from -o)")
    ap.add_argument("--segments", type=int, default=64,
                    help="tessellation resolution for STL/curves")
    ap.add_argument("--binary", action="store_true",
                    help="write binary STL instead of ASCII")
    ap.add_argument("--llm", action="store_true",
                    help="use Claude for prompt parsing if API key is set")
    ap.add_argument("--print", dest="show", action="store_true",
                    help="print the design summary and exit")
    ap.add_argument("--analyze", action="store_true",
                    help="print engineering-grade analysis (NOT certification)")
    ap.add_argument("--material", default="aluminium",
                    help="material for mass properties (default aluminium)")
    args = ap.parse_args(argv)

    try:
        design = _parser.build_from_text(args.prompt, use_llm=args.llm)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(design.summary(), file=sys.stderr)

    if args.analyze:
        from . import engineering
        print(engineering.analyze(design, material=args.material).text())

    if (args.show or args.analyze) and not args.output:
        return 0

    fmt = args.format
    out = args.output
    if not out:
        out = f"{design.name}.stl"
    if not fmt:
        fmt = "scad" if out.lower().endswith(".scad") else "stl"

    if fmt == "scad":
        from . import export_scad
        export_scad.write_scad(design, out, fn=args.segments)
    else:
        from . import mesh
        mesh.write_stl(design, out, seg=args.segments, binary=args.binary)
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
