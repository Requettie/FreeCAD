# Text-to-CAD

Describe a part in plain English and get parametric CAD geometry. Built to run
**inside FreeCAD** as a workbench, **and** standalone from the command line with
**zero dependencies** (it ships its own geometry exporters).

```
python -m texttocad "a 2 metre rocket with 6 fins and 2 stages" -o rocket.stl
python -m texttocad "a turbofan jet engine 3 m long with 28 blades" -o jet.scad
python -m texttocad "a GPU heatsink with 24 fins" -o cooler.stl
python -m texttocad "a 2 m rocket with 6 fins" --analyze        # engineering report
```

> **Not certified.** These are parametric geometry + first-order engineering
> *estimates* from published formulas. They are not FEA/CFD, not physical test,
> and carry no PE stamp or regulatory certification. See *Engineering analysis*
> and *Honest limitations* below.

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
   restart, pick **Text-to-CAD** from the workbench dropdown. You get a toolbar
   with the text prompt **and interactive parameter dialogs for all five
   flagship domains** (rocket, jet engine, CPU cooler, GPU cooler, car) — each
   dialog has an "also run engineering analysis" checkbox. Geometry is built
   with the OpenCASCADE kernel via FreeCAD's `Part` API.
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

## Engineering analysis (estimates, NOT certification)

`--analyze` (CLI) or the dialog checkbox prints first-order engineering metrics,
each tagged with the formula it came from:

| Domain | Metrics | Source |
|---|---|---|
| Rocket | fineness ratio, CNa, CP, CG, **static margin**, ideal Δv | Barrowman 1967; Tsiolkovsky |
| Jet engine | fan disk area, tip speed, **tip Mach**, blade-pass freq, ideal thrust | actuator-disk / fan acoustics |
| Heatsink | fin efficiency, effective area, thermal resistance, junction temp | Incropera fin theory |
| Car | frontal area, Cd·A, drag force & power vs. speed | Hucho |
| Gear | pitch dia, tangential load, Lewis form factor, bending stress | AGMA / Lewis |
| Any | solid-fill mass (upper bound), surface area | geometry |

```
$ python -m texttocad "a 2 m rocket with 6 fins" --analyze
== Rocket aerodynamic & performance estimate ==
(engineering-grade estimate, NOT certified)
  static margin            5.74 cal   [(CP-CG)/d; stable 1-2]
  ideal Delta-v        3.95e+03 m/s   [Tsiolkovsky; Isp=250s, prop frac=0.80]
  ...
```

These are sizing/sanity-check tools. **They do not certify anything** — see
*Honest limitations*.

## Auto-update from your fork

The workbench polls your GitHub fork every 5 minutes (off the UI thread). When
new commits are detected it shows a notice in the **bottom-corner status bar**
with an **Update** button (fast-forward `git pull`), and adds **Check for
Updates** under the File menu. Requires the module to live inside a git checkout
of your fork.

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
