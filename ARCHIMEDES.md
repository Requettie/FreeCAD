# Archimedes

Archimedes is a FreeCAD-based CAD application with a **Text-to-CAD** layer:
describe a part in plain English (or fill in a dialog) and get parametric
geometry, plus first-order **engineering-grade analysis**.

It is built on [FreeCAD](https://www.freecad.org/) (LGPL/GPL — see `LICENSE`)
and adds the Text-to-CAD workbench in [`TextToCAD/`](TextToCAD/).

## What's here

- **`TextToCAD/`** — the Text-to-CAD workbench and its pure-Python core.
  See [`TextToCAD/README.md`](TextToCAD/README.md) for full docs.
- Everything else is the upstream FreeCAD source tree.

## Quick start (Text-to-CAD, no FreeCAD build needed)

```bash
cd TextToCAD
python -m texttocad "a 2 m rocket with 6 fins" -o rocket.stl
python -m texttocad "a 2 m rocket with 6 fins" --analyze     # engineering report
python tests/test_core.py                                    # run the test suite
```

## Capabilities today

- **Domains**: rocket, jet engine, CPU cooler, GPU cooler, car, gear,
  propeller, bolt, bracket, flange, enclosure.
- **Exports**: STL (mesh), OpenSCAD (real CSG booleans), FreeCAD `Part`.
- **Analysis**: Barrowman stability + Δv (rocket), fan tip Mach/thrust (jet),
  thermal resistance (heatsink), drag/power (car), Lewis stress (gear).
- **In-app updater**: status-bar notice + Update button when this repo gets
  new commits.

## Important: not certified

Archimedes produces **geometry and engineering estimates**, not certified
designs. Nothing here is FEA/CFD-validated, physically tested, or
PE-stamped. The analysis figures are sizing/sanity-check tools from published
formulas — treat them as a starting point, not as airworthiness, roadworthiness,
or pressure-vessel certification. See `TextToCAD/README.md` → *Honest
limitations*.
