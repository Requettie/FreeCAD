# Text-to-CAD

Describe a part in plain English and get parametric CAD geometry. Built to run
**inside FreeCAD** as a workbench, **and** standalone from the command line with
**zero dependencies** (it ships its own geometry exporters).

```
python -m texttocad "a 2 metre rocket with 6 fins and 2 stages" -o rocket.stl
python -m texttocad "a turbofan jet engine 3 m long with 28 blades" -o jet.scad
python -m texttocad "a GPU heatsink with 24 fins" -o cooler.stl
python -m texttocad "a 24 tooth gear" --print
```

## What it can build today

| Domain | Example prompt | Parameters understood |
|---|---|---|
| Rocket | `a 2 m rocket with 6 fins and 2 stages` | length, diameter, fin count, stages |
| Jet engine | `a turbofan engine 3 m long with 28 blades` | length, fan diameter, blade count |
| CPU cooler | `a CPU cooler, 50 mm base, 20 fins` | base size, fin count, fin height |
| GPU cooler | `a GPU heatsink with 24 fins` | base size, fin count, fin height |
| Car | `a 4.5 m long sedan, 1.85 m wide` | length, width, height |
| Gear | `a 24 tooth gear` | teeth, thickness |
| Propeller | `a 3 blade propeller 300 mm diameter` | blade count, diameter |
| Bolt | `an M10 bolt 40 mm long` | length, diameter |
| Bracket | `an L-bracket` | (length, width, height, thickness) |
| Flange | `a 6 bolt flange 120 mm diameter` | diameter, bolt count |
| Enclosure | `a project enclosure 120 x 80 x 40 mm` | length, width, height |

Ready-to-open results for each are in [`examples/`](examples/).

## Three ways to use it

1. **FreeCAD workbench** — copy this `TextToCAD/` folder into your FreeCAD
   `Mod/` directory (Help → About FreeCAD → User config, then go up to `Mod/`),
   restart, pick **Text-to-CAD** from the workbench dropdown, click the toolbar
   button and type a prompt. Geometry is built with the OpenCASCADE kernel via
   FreeCAD's `Part` API.
2. **Command line** — `python -m texttocad "..." -o out.stl|out.scad`.
   `.scad` gives true CSG booleans (open in OpenSCAD); `.stl` gives a viewable
   mesh anywhere.
3. **Library** —
   ```python
   import texttocad
   design = texttocad.design_from_text("a 24 tooth gear")  # pure spec
   texttocad.text_to_stl("a 24 tooth gear", "gear.stl")
   texttocad.text_to_scad("a 6 bolt flange", "flange.scad")
   ```

## Optional: smarter parsing with Claude

The prompt parser is fully offline and deterministic. If you set
`ANTHROPIC_API_KEY` (and `pip install anthropic`), pass `--llm` to let Claude
handle messier prompts; it falls back to the rule-based parser automatically.

## Architecture

```
texttocad/
  spec.py         pure-Python parametric model (solids, booleans, arrays)
  parser.py       prompt -> (domain, parameters); offline + word-boundary safe
  generators.py   one parametric template per domain -> Design
  export_scad.py  Design -> OpenSCAD (real union/difference/intersection)
  mesh.py         Design -> triangle mesh -> ASCII/binary STL (no deps)
  builder.py      Design -> FreeCAD Part geometry (only file importing FreeCAD)
  llm.py          optional Claude-backed parsing
  __main__.py     CLI
InitGui.py        FreeCAD workbench registration
tests/test_core.py  15 tests, run without FreeCAD
```

The core never imports FreeCAD, so it is unit-tested in plain Python:

```
python tests/test_core.py
```

## Honest limitations

These are **parametric starting templates**, not certified engineering models —
a rocket here is nose cone + body + fins + nozzle, not a flight-ready vehicle.
STL export approximates `cut`/`common` booleans by meshing the first operand
(STL has no CSG engine); use the OpenSCAD or FreeCAD path for exact booleans.
Adding a domain is a single function in `generators.py` plus an alias in
`parser.py`.
