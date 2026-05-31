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
