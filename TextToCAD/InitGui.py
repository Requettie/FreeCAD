"""
FreeCAD workbench: Text-to-CAD.

Provides
  * a natural-language prompt command,
  * interactive parameter dialogs for the five flagship domains
    (rocket, jet engine, CPU cooler, GPU cooler, car),
  * an engineering-grade analysis report (clearly NOT certification),
  * an in-app updater: a status-bar notice (bottom corner) that appears when
    your GitHub fork has new commits, plus File-menu "Check for Updates" /
    "Install Update" actions.

Install: copy this TextToCAD/ folder into FreeCAD's Mod/ directory, restart,
and choose "Text-to-CAD" from the workbench dropdown.
"""

import os
import sys

import FreeCAD as App
import FreeCADGui as Gui

# --- Qt import shim (FreeCAD ships PySide2/6, older builds PySide) ---------- #
try:
    from PySide2 import QtCore, QtGui, QtWidgets
except Exception:  # pragma: no cover
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except Exception:
        from PySide import QtCore, QtGui  # type: ignore
        QtWidgets = QtGui

_HERE = os.path.dirname(__file__)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_UPDATE_INTERVAL_MS = 5 * 60 * 1000   # poll every 5 minutes


def _pkg():
    import texttocad
    return texttocad


def _build_and_report(design, analyze=False, analyze_opts=None):
    """Build a Design into FreeCAD and optionally show its analysis."""
    from texttocad import builder
    doc = builder.build(design)
    App.Console.PrintMessage(f"Text-to-CAD: built '{doc.Name}'.\n")
    if analyze:
        from texttocad import engineering
        rep = engineering.analyze(design, **(analyze_opts or {}))
        App.Console.PrintMessage(rep.text() + "\n")
        QtWidgets.QMessageBox.information(None, "Engineering analysis", rep.text())
    return doc


# --------------------------------------------------------------------------- #
# Generic parameter dialog
# --------------------------------------------------------------------------- #
class ParamDialog(QtWidgets.QDialog):
    """Build a form from (label, key, kind, default) tuples; kind in
    {'int','float'}. Returns a params dict via .values()."""

    def __init__(self, title, fields):
        super().__init__()
        self.setWindowTitle(title)
        self._fields = fields
        self._widgets = {}
        form = QtWidgets.QFormLayout(self)
        for label, key, kind, default in fields:
            if kind == "int":
                w = QtWidgets.QSpinBox()
                w.setRange(1, 100000)
                w.setValue(int(default))
            else:
                w = QtWidgets.QDoubleSpinBox()
                w.setRange(0.0, 1e7)
                w.setDecimals(2)
                w.setValue(float(default))
            self._widgets[key] = (w, kind)
            form.addRow(label, w)
        self._analyze = QtWidgets.QCheckBox("Also run engineering analysis "
                                            "(estimate, NOT certified)")
        form.addRow(self._analyze)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self):
        out = {}
        for key, (w, kind) in self._widgets.items():
            out[key] = int(w.value()) if kind == "int" else float(w.value())
        return out

    def analyze_requested(self):
        return self._analyze.isChecked()


# domain -> (dialog title, generator name, field specs)
_DOMAIN_DIALOGS = {
    "Rocket": ("rocket", [
        ("Total length (mm)", "total_length", "float", 2000),
        ("Body diameter (mm)", "body_diameter", "float", 100),
        ("Fin count", "fin_count", "int", 4),
        ("Stages", "stages", "int", 1)]),
    "Jet engine": ("jet_engine", [
        ("Length (mm)", "length", "float", 3000),
        ("Fan diameter (mm)", "fan_diameter", "float", 1200),
        ("Blade count", "blade_count", "int", 24)]),
    "CPU cooler": ("cpu", [
        ("Base size (mm)", "base", "float", 40),
        ("Fin count", "fin_count", "int", 16),
        ("Fin height (mm)", "fin_height", "float", 30)]),
    "GPU cooler": ("gpu", [
        ("Base size (mm)", "base", "float", 55),
        ("Fin count", "fin_count", "int", 24),
        ("Fin height (mm)", "fin_height", "float", 40)]),
    "Car": ("car", [
        ("Length (mm)", "length", "float", 4500),
        ("Width (mm)", "width", "float", 1850),
        ("Height (mm)", "height", "float", 1450)]),
}


def _make_domain_command(label, gen_name, fields):
    class _Cmd:
        def GetResources(self):
            return {"MenuText": label,
                    "ToolTip": f"Design a {label.lower()} parametrically"}

        def IsActive(self):
            return True

        def Activated(self):
            dlg = ParamDialog(label, fields)
            if dlg.exec_() != QtWidgets.QDialog.Accepted:
                return
            gen = _pkg().generators.REGISTRY[gen_name]
            try:
                design = gen(**dlg.values())
                _build_and_report(design, analyze=dlg.analyze_requested())
            except Exception as e:  # pragma: no cover
                QtWidgets.QMessageBox.warning(None, label, str(e))
    return _Cmd()


# --------------------------------------------------------------------------- #
# Text-prompt command
# --------------------------------------------------------------------------- #
class PromptCommand:
    def GetResources(self):
        return {"MenuText": "Text to CAD…",
                "ToolTip": "Describe a part in plain English and generate it"}

    def IsActive(self):
        return True

    def Activated(self):
        text, ok = QtWidgets.QInputDialog.getText(
            None, "Text to CAD",
            "Describe what to build (e.g. 'a 2 m rocket with 6 fins',\n"
            "'a GPU heatsink with 24 fins', 'a 4.5 m sedan'):")
        if not ok or not text.strip():
            return
        use_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))
        try:
            design = _pkg().design_from_text(text, use_llm=use_llm)
            _build_and_report(design)
        except Exception as e:
            QtWidgets.QMessageBox.warning(None, "Text to CAD", str(e))


# --------------------------------------------------------------------------- #
# Updater: status-bar notice + commands
# --------------------------------------------------------------------------- #
class _CheckWorker(QtCore.QThread):
    """Runs git fetch + status off the UI thread."""
    done = QtCore.Signal(object)

    def __init__(self, repo):
        super().__init__()
        self._repo = repo

    def run(self):
        try:
            from texttocad import updater
            self.done.emit(updater.check_for_updates(self._repo))
        except Exception as e:  # pragma: no cover
            self.done.emit({"ok": False, "error": str(e)})


class UpdateNotifier(QtCore.QObject):
    """Owns the status-bar widgets and the polling timer."""

    def __init__(self):
        super().__init__()
        from texttocad import updater
        self.repo = updater.repo_root(_HERE)
        self.label = None
        self.button = None
        self._worker = None
        if self.repo:
            self._install_widgets()
            self._timer = QtCore.QTimer(self)
            self._timer.timeout.connect(self.check)
            self._timer.start(_UPDATE_INTERVAL_MS)
            QtCore.QTimer.singleShot(3000, self.check)  # initial check

    def _install_widgets(self):
        sb = Gui.getMainWindow().statusBar()
        self.label = QtWidgets.QLabel("")
        self.button = QtWidgets.QToolButton()
        self.button.setText("Update")
        self.button.clicked.connect(self.install)
        self.label.hide()
        self.button.hide()
        sb.addPermanentWidget(self.label)
        sb.addPermanentWidget(self.button)

    def check(self):
        if not self.repo or (self._worker and self._worker.isRunning()):
            return
        self._worker = _CheckWorker(self.repo)
        self._worker.done.connect(self._on_result)
        self._worker.start()

    def _on_result(self, res):
        if not res or not res.get("ok"):
            return
        if res.get("update_available"):
            n = res["behind"]
            self.label.setText(f"⬆ Text-to-CAD: {n} update"
                               f"{'s' if n != 1 else ''} available "
                               f"— {res.get('latest','')}")
            self.label.show()
            self.button.show()
        else:
            self.label.hide()
            self.button.hide()

    def install(self):
        from texttocad import updater
        ok, msg = updater.pull(self.repo)
        if ok:
            QtWidgets.QMessageBox.information(
                None, "Update", "Updated. Restart FreeCAD to load changes.\n\n"
                + msg)
            self.label.hide()
            self.button.hide()
        else:
            QtWidgets.QMessageBox.warning(None, "Update failed", msg)


# module-level so it isn't garbage-collected
_NOTIFIER = None


class CheckUpdateCommand:
    def GetResources(self):
        return {"MenuText": "Check for Updates",
                "ToolTip": "Check your GitHub fork for new commits"}

    def IsActive(self):
        return _NOTIFIER is not None and _NOTIFIER.repo is not None

    def Activated(self):
        from texttocad import updater
        res = updater.check_for_updates(_NOTIFIER.repo)
        if not res.get("ok"):
            QtWidgets.QMessageBox.warning(None, "Check for Updates",
                                          res.get("error", "unknown error"))
        elif res.get("update_available"):
            _NOTIFIER._on_result(res)
            QtWidgets.QMessageBox.information(
                None, "Check for Updates",
                f"{res['behind']} update(s) available.\nLatest: {res['latest']}")
        else:
            QtWidgets.QMessageBox.information(None, "Check for Updates",
                                              "You are up to date.")


# --------------------------------------------------------------------------- #
# Workbench
# --------------------------------------------------------------------------- #
class TextToCADWorkbench(Gui.Workbench):
    MenuText = "Text-to-CAD"
    ToolTip = "Generate parametric CAD from prompts and parameter dialogs"

    def Initialize(self):
        cmds = ["TextToCAD_Prompt"]
        Gui.addCommand("TextToCAD_Prompt", PromptCommand())
        for label, (gen_name, fields) in _DOMAIN_DIALOGS.items():
            cid = "TextToCAD_" + gen_name
            Gui.addCommand(cid, _make_domain_command(label, gen_name, fields))
            cmds.append(cid)
        Gui.addCommand("TextToCAD_CheckUpdate", CheckUpdateCommand())

        self.appendToolbar("Text-to-CAD", cmds)
        self.appendMenu("Text-to-CAD", cmds)
        self.appendMenu("Text-to-CAD", ["TextToCAD_CheckUpdate"])
        self._add_update_to_file_menu()

        global _NOTIFIER
        if _NOTIFIER is None:
            try:
                _NOTIFIER = UpdateNotifier()
            except Exception as e:  # pragma: no cover
                App.Console.PrintWarning(f"Text-to-CAD updater disabled: {e}\n")

    def _add_update_to_file_menu(self):
        """Best-effort: place 'Check for Updates' under the native File menu."""
        try:
            mw = Gui.getMainWindow()
            for act in mw.menuBar().actions():
                if act.text().replace("&", "").strip().lower() == "file":
                    menu = act.menu()
                    menu.addSeparator()
                    a = menu.addAction("Check for Updates…")
                    a.triggered.connect(lambda: CheckUpdateCommand().Activated())
                    break
        except Exception:
            pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(TextToCADWorkbench())
