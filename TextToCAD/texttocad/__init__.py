"""Text-to-CAD core package (engine-agnostic + FreeCAD builder)."""

from . import generators, parser, spec  # noqa: F401

__version__ = "0.1.0"


def design_from_text(text: str, use_llm: bool = False):
    """Prompt -> Design (pure spec, no FreeCAD needed)."""
    return parser.build_from_text(text, use_llm=use_llm)


def build_from_text(text: str, use_llm: bool = False, doc=None):
    """Prompt -> geometry in a FreeCAD document (requires FreeCAD)."""
    from . import builder
    return builder.build(parser.build_from_text(text, use_llm=use_llm), doc=doc)


def text_to_stl(text: str, path: str, seg: int = 64, binary: bool = False,
                use_llm: bool = False) -> str:
    """Prompt -> STL file (pure Python, no FreeCAD needed)."""
    from . import mesh
    return mesh.write_stl(design_from_text(text, use_llm=use_llm), path,
                          seg=seg, binary=binary)


def text_to_scad(text: str, path: str, fn: int = 64, use_llm: bool = False) -> str:
    """Prompt -> OpenSCAD file (real CSG booleans, no FreeCAD needed)."""
    from . import export_scad
    return export_scad.write_scad(design_from_text(text, use_llm=use_llm),
                                  path, fn=fn)


def analyze_text(text: str, use_llm: bool = False, **opts):
    """Prompt -> engineering-grade analysis Report (NOT certification)."""
    from . import engineering
    return engineering.analyze(design_from_text(text, use_llm=use_llm), **opts)
