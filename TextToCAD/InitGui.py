"""
FreeCAD workbench registration for Text-to-CAD.

Drop the whole ``TextToCAD`` folder into your FreeCAD ``Mod`` directory
(Help > About > User config -> .../Mod/), restart FreeCAD, and pick
"Text-to-CAD" from the workbench dropdown.
"""

import FreeCAD as App
import FreeCADGui as Gui


class TextToCADCommand:
    """Prompt the user for text, then build geometry."""

    def GetResources(self):
        return {
            "MenuText": "Text to CAD…",
            "ToolTip": "Describe a part in plain English and generate it",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from PySide import QtGui
        import os
        # local import so the package resolves relative to this file
        import sys
        here = os.path.dirname(__file__)
        if here not in sys.path:
            sys.path.insert(0, here)
        import texttocad

        text, ok = QtGui.QInputDialog.getText(
            None, "Text to CAD",
            "Describe what to build\n"
            "(e.g. 'a 2 m rocket with 6 fins', 'a GPU heatsink with 24 fins',\n"
            "'a 4.5 m sedan', 'a turbofan engine 3 m long'):",
        )
        if not ok or not text.strip():
            return
        use_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))
        try:
            doc = texttocad.build_from_text(text, use_llm=use_llm)
            App.Console.PrintMessage(
                f"Text-to-CAD: built '{doc.Name}' from prompt.\n")
        except Exception as e:
            QtGui.QMessageBox.warning(None, "Text to CAD", str(e))


class TextToCADWorkbench(Gui.Workbench):
    MenuText = "Text-to-CAD"
    ToolTip = "Generate parametric CAD from natural-language prompts"

    def Initialize(self):
        Gui.addCommand("TextToCAD_Prompt", TextToCADCommand())
        self.appendToolbar("Text-to-CAD", ["TextToCAD_Prompt"])
        self.appendMenu("Text-to-CAD", ["TextToCAD_Prompt"])

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(TextToCADWorkbench())
