"""FiveHub windows inside Houdini.

Qt dialogs (PySide2 on older builds, PySide6 on H20.5+) parented to the
Houdini main window, styled in the same pure black & white language as the
standalone hub app. The dialogs only collect intent — every action (saving,
loading, publishing) is driven by fivehub_houdini after they close.
"""

import os
import sys

import hou

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

try:
    from PySide2 import QtCore, QtWidgets
except ImportError:  # Houdini 20.5+
    from PySide6 import QtCore, QtWidgets

from fivehub import config
from fivehub.project import get_project, list_projects

# Mainly white, black ink, rounded — red appears only when a publish is
# blocked (the failed report heading). Matches the hub app's design system.
STYLE = """
QWidget { background: transparent; color: #0b0b0c;
    font-family: "Satoshi", "SF Pro Text", "Segoe UI", "Helvetica Neue",
    Arial, sans-serif;
    font-size: 12px; }
/* The ID selector outranks every type rule (and Houdini's own dark
   stylesheet), so the dialog base is ALWAYS the light wash — without it
   the QWidget rule above turns the dialog transparent and Houdini's
   near-black shell bleeds through behind ink-colored text. */
QDialog#fivehubDialog { background: #f5f5f7; }
QLabel { background: transparent; }
QLabel#heading { font-family: "Satoshi Black", "Satoshi", sans-serif;
    font-size: 21px; font-weight: 900; }
QLabel#headingFail { font-family: "Satoshi Black", "Satoshi", sans-serif;
    font-size: 21px; font-weight: 900; color: #ff3b30; }
QLabel#hint { font-size: 10px; font-weight: 600; letter-spacing: 1px;
    color: #6e6e73; }
QLabel#context { background: #ffffff; border: 1px solid rgba(0, 0, 0, 40);
    border-radius: 10px; padding: 9px 12px; font-weight: 600; }
QLineEdit, QComboBox, QPlainTextEdit, QListWidget {
    background: #ffffff; color: #0b0b0c;
    border: 1px solid rgba(0, 0, 0, 40); border-radius: 10px;
    padding: 7px 10px;
    selection-background-color: #0b0b0c; selection-color: #ffffff; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {
    border: 1px solid rgba(0, 0, 0, 90); }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView { background: #ffffff; color: #0b0b0c;
    border: 1px solid rgba(0, 0, 0, 40); border-radius: 10px;
    selection-background-color: #0b0b0c; selection-color: #ffffff;
    outline: none; }
QComboBox QLineEdit { background: #ffffff; color: #0b0b0c; border: none;
    padding: 0; selection-background-color: #0b0b0c;
    selection-color: #ffffff; }
QListWidget::item { padding: 9px; border-radius: 8px; }
QListWidget::item:selected { background: #0b0b0c; color: #ffffff; }
QPushButton { background: #ffffff; color: #0b0b0c;
    border: 1px solid rgba(0, 0, 0, 40); border-radius: 16px;
    padding: 8px 22px; font-weight: 600; }
QPushButton:hover { background: #ececee; }
QPushButton:pressed { background: #e0e0e2; }
QPushButton#primary { background: #0b0b0c; color: #ffffff;
    border: 1px solid #0b0b0c; }
QPushButton#primary:hover { background: #26262a; }
QScrollBar:vertical { background: transparent; width: 12px; }
QScrollBar::handle:vertical { background: rgba(0, 0, 0, 60);
    border-radius: 6px; min-height: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""


def exec_dialog(dialog):
    return dialog.exec_() if hasattr(dialog, "exec_") else dialog.exec()


def _label(text, object_name=None):
    widget = QtWidgets.QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    return widget


NEW_MARKER = "__fivehub_new__"


class ContextWidget(QtWidgets.QWidget):
    """Project / kind / entity / task cascade — selection only, so a typo
    can never invent an entity. When ``editable``, explicit "+ NEW …"
    entries ask for a name (created on confirm by the caller)."""

    changed = QtCore.Signal()

    def __init__(self, editable=False, parent=None):
        super(ContextWidget, self).__init__(parent)
        self.editable = editable

        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)

        self.project_combo = QtWidgets.QComboBox()
        self.kind_combo = QtWidgets.QComboBox()
        for kind in config.KINDS:
            self.kind_combo.addItem(kind.upper(), kind)
        self.entity_combo = QtWidgets.QComboBox()
        self.task_combo = QtWidgets.QComboBox()
        if editable:
            self.entity_combo.activated.connect(self._maybe_create_entity)
            self.task_combo.activated.connect(self._maybe_create_task)

        for column, (title, widget) in enumerate(
            (
                ("PROJECT", self.project_combo),
                ("TYPE", self.kind_combo),
                ("ASSET / SHOT", self.entity_combo),
                ("TASK", self.task_combo),
            )
        ):
            grid.addWidget(_label(title, "hint"), 0, column)
            grid.addWidget(widget, 1, column)
            grid.setColumnStretch(column, 1 if column != 1 else 0)

        self._projects = [info["name"] for info in list_projects()]
        self.project_combo.addItems(self._projects)

        self.project_combo.currentIndexChanged.connect(self._refresh_entities)
        self.kind_combo.currentIndexChanged.connect(self._refresh_entities)
        self.entity_combo.currentIndexChanged.connect(self._refresh_tasks)
        self.entity_combo.currentTextChanged.connect(lambda _t: self.changed.emit())
        self.task_combo.currentTextChanged.connect(lambda _t: self.changed.emit())
        self._refresh_entities()

    def has_projects(self):
        return bool(self._projects)

    def _project(self):
        name = self.project_combo.currentText().strip()
        if not name:
            return None
        try:
            return get_project(name)
        except ValueError:
            return None

    def _refresh_entities(self):
        project = self._project()
        kind = self.kind_combo.currentData()
        current = self.entity_combo.currentText()
        self.entity_combo.blockSignals(True)
        self.entity_combo.clear()
        if project:
            for entity in project.entities(kind):
                self.entity_combo.addItem(entity["name"])
        if self.editable:
            self.entity_combo.addItem("+ NEW %s…" % kind.upper(), NEW_MARKER)
        found = self.entity_combo.findText(current)
        if found >= 0:
            self.entity_combo.setCurrentIndex(found)
        self.entity_combo.blockSignals(False)
        self._refresh_tasks()

    def _refresh_tasks(self):
        project = self._project()
        kind = self.kind_combo.currentData()
        entity = self._value(self.entity_combo)
        current = self.task_combo.currentText()
        self.task_combo.blockSignals(True)
        self.task_combo.clear()
        existing = []
        if project and entity:
            existing = [task["name"] for task in project.tasks(kind, entity)]
            self.task_combo.addItems(existing)
        if self.editable:
            for suggestion in config.DEFAULT_TASKS:
                if suggestion not in existing:
                    self.task_combo.addItem(suggestion)
            self.task_combo.addItem("+ NEW TASK…", NEW_MARKER)
        found = self.task_combo.findText(current)
        if found >= 0:
            self.task_combo.setCurrentIndex(found)
        self.task_combo.blockSignals(False)
        self.changed.emit()

    def _value(self, combo):
        if combo.currentData() == NEW_MARKER:
            return ""
        return combo.currentText().strip()

    def _create_via(self, combo, prompt):
        name, ok = QtWidgets.QInputDialog.getText(self, "FIVE HUB", prompt)
        name = (name or "").strip()
        if ok and name:
            insert_at = combo.count() - 1  # just before the "+ NEW …" entry
            combo.insertItem(insert_at, name)
            combo.setCurrentIndex(insert_at)
        else:
            combo.setCurrentIndex(0 if combo.count() > 1 else -1)

    def _maybe_create_entity(self, index):
        if self.entity_combo.itemData(index) == NEW_MARKER:
            self._create_via(
                self.entity_combo,
                "Name of the new %s:" % self.kind_combo.currentData(),
            )

    def _maybe_create_task(self, index):
        if self.task_combo.itemData(index) == NEW_MARKER:
            self._create_via(self.task_combo, "Name of the new task:")

    def context(self):
        return {
            "project": self.project_combo.currentText().strip(),
            "kind": self.kind_combo.currentData(),
            "entity": self._value(self.entity_combo),
            "task": self._value(self.task_combo).lower(),
        }

    def set_context(self, context):
        if not context:
            return
        index = self.project_combo.findText(context.get("project", ""))
        if index >= 0:
            self.project_combo.setCurrentIndex(index)
        kind_index = self.kind_combo.findData(context.get("kind", "asset"))
        if kind_index >= 0:
            self.kind_combo.setCurrentIndex(kind_index)
        self._refresh_entities()
        for combo, key in ((self.entity_combo, "entity"), (self.task_combo, "task")):
            value = context.get(key, "")
            found = combo.findText(value)
            if found >= 0:
                combo.setCurrentIndex(found)
            elif self.editable and value:
                # Incoming context (scene path, FH_* env) that isn't in the
                # project yet — a real selectable item, never free text.
                insert_at = max(combo.count() - 1, 0)
                combo.insertItem(insert_at, value)
                combo.setCurrentIndex(insert_at)


class _BaseDialog(QtWidgets.QDialog):
    def __init__(self, heading, parent=None, heading_object="heading"):
        super(_BaseDialog, self).__init__(parent or hou.qt.mainWindow())
        self.setObjectName("fivehubDialog")
        self.setStyleSheet(STYLE)
        self.setWindowTitle("FIVE HUB")
        # Qt 5 dialogs grow a "?" (What's This) title-bar button on Windows
        # that does nothing here — drop it.
        self.setWindowFlags(
            self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint
        )
        self.layout_ = QtWidgets.QVBoxLayout(self)
        self.layout_.setContentsMargins(26, 26, 26, 26)
        self.layout_.setSpacing(16)
        self.layout_.addWidget(_label(heading, heading_object))

    def add_buttons(self, confirm_text):
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        cancel = QtWidgets.QPushButton("CANCEL")
        cancel.clicked.connect(self.reject)
        confirm = QtWidgets.QPushButton(confirm_text)
        confirm.setObjectName("primary")
        confirm.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(confirm)
        self.layout_.addLayout(row)
        return confirm


class SaveSceneDialog(_BaseDialog):
    """Save the current scene into an asset/shot task, versioned + noted."""

    def __init__(self, prefill=None, parent=None):
        super(SaveSceneDialog, self).__init__("SAVE SCENE", parent)
        self.resize(680, 320)

        self.context_widget = ContextWidget(editable=True)
        self.layout_.addWidget(self.context_widget)

        # Scene name: several fx setups on one shot save as separate named
        # streams, each versioned on its own. Editable combo — pick an
        # existing name (no mistype) or type a new one.
        self.layout_.addWidget(_label("SCENE NAME", "hint"))
        self.scene_combo = QtWidgets.QComboBox()
        self.scene_combo.setEditable(True)
        self.layout_.addWidget(self.scene_combo)

        self.layout_.addWidget(_label("NOTES", "hint"))
        self.notes = QtWidgets.QPlainTextEdit()
        self.notes.setFixedHeight(80)
        self.layout_.addWidget(self.notes)

        self.target_label = _label("", "hint")
        self.layout_.addWidget(self.target_label)

        self.add_buttons("SAVE")
        self.context_widget.changed.connect(self._refresh_scene_names)
        self.scene_combo.currentTextChanged.connect(
            lambda _t: self._update_target())
        self.context_widget.set_context(prefill)
        self._prefill_name = (prefill or {}).get("scene_name", "")
        self._refresh_scene_names()

    def _refresh_scene_names(self):
        context = self.context_widget.context()
        current = self.scene_combo.currentText() or self._prefill_name
        self._prefill_name = ""
        existing = []
        try:
            project = get_project(context["project"])
            existing = sorted({
                scene["name"]
                for scene in project.scenes(
                    context["kind"], context["entity"], context["task"])
            })
        except ValueError:
            pass
        self.scene_combo.blockSignals(True)
        self.scene_combo.clear()
        self.scene_combo.addItems(existing or ["main"])
        if current:
            self.scene_combo.setEditText(current)
        elif "main" in (existing or ["main"]):
            self.scene_combo.setEditText("main")
        self.scene_combo.blockSignals(False)
        self._update_target()

    def _scene_name(self):
        return (self.scene_combo.currentText().strip() or "main")

    def _update_target(self):
        context = self.context_widget.context()
        if not (context["project"] and context["entity"] and context["task"]):
            self.target_label.setText("PICK A PROJECT / ENTITY / TASK")
            return
        name = self._scene_name()
        version = 1
        try:
            project = get_project(context["project"])
            version = project.next_scene_version(
                context["kind"], context["entity"], context["task"], name
            )
        except ValueError:
            pass  # entity or task does not exist yet -> first version
        from fivehub_houdini import scene_extension

        self.target_label.setText(
            "WILL SAVE  %s"
            % config.scene_file_name(
                context["entity"], context["task"], version,
                scene_extension(), name,
            )
        )

    def values(self):
        return (self.context_widget.context(),
                self.notes.toPlainText().strip(), self._scene_name())


class LoadSceneDialog(_BaseDialog):
    """Pick a scene version of an asset/shot task to open."""

    def __init__(self, prefill=None, parent=None):
        super(LoadSceneDialog, self).__init__("LOAD SCENE", parent)
        self.resize(760, 480)

        self.context_widget = ContextWidget(editable=False)
        self.layout_.addWidget(self.context_widget)

        self.scene_list = QtWidgets.QListWidget()
        self.layout_.addWidget(self.scene_list, 1)

        self.add_buttons("OPEN")
        self.context_widget.changed.connect(self._refresh_scenes)
        self.context_widget.set_context(prefill)
        self._refresh_scenes()
        self.scene_list.itemDoubleClicked.connect(lambda _item: self.accept())

    def _refresh_scenes(self):
        self.scene_list.clear()
        context = self.context_widget.context()
        if not (context["project"] and context["entity"] and context["task"]):
            return
        try:
            project = get_project(context["project"])
            scenes = project.scenes(context["kind"], context["entity"], context["task"])
        except ValueError:
            return
        for scene in scenes:
            text = "%s   %s   %s   %s" % (
                scene.get("name", "main"),
                config.version_label(scene["version"]),
                scene["user"] or "-",
                (scene["created_at"] or "").replace("T", " ").rstrip("Z"),
            )
            if scene["notes"]:
                text += "\n%s" % scene["notes"]
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, scene["file"])
            self.scene_list.addItem(item)
        if scenes:
            self.scene_list.setCurrentRow(0)

    def selected_file(self):
        item = self.scene_list.currentItem()
        return item.data(QtCore.Qt.UserRole) if item else None


class PublishDialog(_BaseDialog):
    """Define what a publish is before it runs. The context is NOT a
    choice: it comes from the saved scene — the dialog only shows it."""

    def __init__(self, context, parent=None):
        super(PublishDialog, self).__init__("PUBLISH", parent)
        self.resize(640, 340)
        self.context = dict(context)

        banner = _label(
            "%s   ·   %s %s   ·   %s"
            % (
                context["project"],
                context["kind"].upper(),
                context["entity"],
                context["task"],
            ),
            "context",
        )
        self.layout_.addWidget(banner)
        self.layout_.addWidget(
            _label("CONTEXT COMES FROM THE SAVED SCENE — SAVE ELSEWHERE TO CHANGE IT", "hint")
        )

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)

        self.name_edit = QtWidgets.QLineEdit(context["entity"])
        self.format_combo = QtWidgets.QComboBox()
        for format_name in config.FORMATS:
            self.format_combo.addItem(format_name.upper(), format_name)
        self.variant_edit = QtWidgets.QLineEdit("default")
        self.comment_edit = QtWidgets.QLineEdit()

        for column, (title, widget) in enumerate(
            (
                ("PUBLISH NAME", self.name_edit),
                ("FORMAT", self.format_combo),
                ("VARIANT", self.variant_edit),
            )
        ):
            grid.addWidget(_label(title, "hint"), 0, column)
            grid.addWidget(widget, 1, column)
        grid.addWidget(_label("COMMENT", "hint"), 2, 0, 1, 3)
        grid.addWidget(self.comment_edit, 3, 0, 1, 3)
        self.layout_.addLayout(grid)

        animation_row = QtWidgets.QHBoxLayout()
        self.animated_check = QtWidgets.QCheckBox("ANIMATED (BAKE FRAME RANGE)")
        self.frame_start_edit = QtWidgets.QLineEdit()
        self.frame_start_edit.setFixedWidth(70)
        self.frame_end_edit = QtWidgets.QLineEdit()
        self.frame_end_edit.setFixedWidth(70)
        animation_row.addWidget(self.animated_check)
        animation_row.addWidget(_label("RANGE", "hint"))
        animation_row.addWidget(self.frame_start_edit)
        animation_row.addWidget(self.frame_end_edit)
        animation_row.addStretch(1)
        self.layout_.addLayout(animation_row)

        self.hint_label = _label(
            "USD PUBLISHES RUN FULL VALIDATION — ERRORS BLOCK THE PUBLISH", "hint"
        )
        self.layout_.addWidget(self.hint_label)

        self.add_buttons("VALIDATE + PUBLISH")

    def set_frame_range(self, start, end):
        self.frame_start_edit.setText(str(int(start)))
        self.frame_end_edit.setText(str(int(end)))

    def values(self):
        def _int(edit, fallback):
            try:
                return int(float(edit.text()))
            except (TypeError, ValueError):
                return fallback

        return {
            "context": dict(self.context),
            "name": self.name_edit.text().strip(),
            "format": self.format_combo.currentData(),
            "variant": self.variant_edit.text().strip() or "default",
            "comment": self.comment_edit.text().strip(),
            "animated": self.animated_check.isChecked(),
            "frame_start": _int(self.frame_start_edit, 1001),
            "frame_end": _int(self.frame_end_edit, 1100),
        }


class LoadAssetDialog(_BaseDialog):
    """Pick a publish of an asset/shot task to bring into the scene."""

    def __init__(self, prefill=None, parent=None):
        super(LoadAssetDialog, self).__init__("LOAD PUBLISHED ASSET", parent)
        self.resize(760, 480)

        self.context_widget = ContextWidget(editable=False)
        self.layout_.addWidget(self.context_widget)

        self.publish_list = QtWidgets.QListWidget()
        self.layout_.addWidget(self.publish_list, 1)

        self.add_buttons("IMPORT")
        self.context_widget.changed.connect(self._refresh_publishes)
        self.context_widget.set_context(prefill)
        self._refresh_publishes()
        self.publish_list.itemDoubleClicked.connect(lambda _item: self.accept())

    def _refresh_publishes(self):
        self.publish_list.clear()
        context = self.context_widget.context()
        if not (context["project"] and context["entity"] and context["task"]):
            return
        try:
            project = get_project(context["project"])
            publishes = project.publishes(
                context["kind"], context["entity"], context["task"]
            )
        except ValueError:
            return
        for row in publishes:
            if not row["version"]:
                continue  # blocked attempts have nothing to import
            text = "%s  %s  %s   %s" % (
                row["format"].upper(),
                config.version_label(row["version"]),
                row["variant"],
                row["comment"] or "",
            )
            item = QtWidgets.QListWidgetItem(text.rstrip())
            item.setData(QtCore.Qt.UserRole, dict(row))
            self.publish_list.addItem(item)
        if self.publish_list.count():
            self.publish_list.setCurrentRow(0)

    def selected_publish(self):
        item = self.publish_list.currentItem()
        return item.data(QtCore.Qt.UserRole) if item else None


class RenderDialog(_BaseDialog):
    """Queue a render of the current saved scene: pick ROP + frame range."""

    def __init__(self, context, rops, frame_start, frame_end, scene_version,
                 parent=None):
        super(RenderDialog, self).__init__("SUBMIT RENDER", parent)
        self.resize(600, 300)

        banner = _label(
            "%s   ·   %s %s   ·   %s   ·   SCENE V%03d"
            % (context["project"], context["kind"].upper(), context["entity"],
               context["task"], scene_version),
            "context",
        )
        self.layout_.addWidget(banner)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)

        self.rop_combo = QtWidgets.QComboBox()
        for rop in rops:
            self.rop_combo.addItem(rop)
        self.start_edit = QtWidgets.QLineEdit(str(int(frame_start)))
        self.end_edit = QtWidgets.QLineEdit(str(int(frame_end)))
        self.step_edit = QtWidgets.QLineEdit("1")

        for column, (title, widget, stretch) in enumerate(
            (
                ("ROP", self.rop_combo, 3),
                ("START", self.start_edit, 1),
                ("END", self.end_edit, 1),
                ("STEP", self.step_edit, 1),
            )
        ):
            grid.addWidget(_label(title, "hint"), 0, column)
            grid.addWidget(widget, 1, column)
            grid.setColumnStretch(column, stretch)
        self.layout_.addLayout(grid)

        self.layout_.addWidget(
            _label("RUNS ON A FIVEHUB WORKER — FRAMES BECOME A RENDER PUBLISH", "hint")
        )
        self.add_buttons("QUEUE RENDER")

    def values(self):
        def _int(edit, fallback):
            try:
                return int(float(edit.text()))
            except (TypeError, ValueError):
                return fallback

        return {
            "rop": self.rop_combo.currentText(),
            "frame_start": _int(self.start_edit, 1001),
            "frame_end": _int(self.end_edit, 1100),
            "step": max(1, _int(self.step_edit, 1)),
        }


class ToolsDialog(_BaseDialog):
    """The drop-in pipeline tools, one click away."""

    def __init__(self, labels, parent=None):
        super(ToolsDialog, self).__init__("PIPELINE TOOLS", parent)
        self.resize(460, 380)
        self.tool_list = QtWidgets.QListWidget()
        for label in labels:
            self.tool_list.addItem(label)
        if labels:
            self.tool_list.setCurrentRow(0)
        self.layout_.addWidget(self.tool_list, 1)
        self.layout_.addWidget(
            _label("ADD YOUR OWN IN fivehub/tools/ — HDAS GO IN houdini/otls/", "hint")
        )
        self.add_buttons("RUN")
        self.tool_list.itemDoubleClicked.connect(lambda _item: self.accept())

    def selected_index(self):
        row = self.tool_list.currentRow()
        return row if row >= 0 else None


class ReportDialog(_BaseDialog):
    """Pass/fail validation report. The failed heading is the one place
    the accent red appears inside Houdini."""

    def __init__(self, report, extra="", parent=None):
        heading = "VALIDATION PASSED" if report.passed else "VALIDATION FAILED"
        super(ReportDialog, self).__init__(
            heading, parent, heading_object="heading" if report.passed else "headingFail"
        )
        self.resize(720, 560)

        text = report.to_text()
        if extra:
            text += "\n\n" + extra
        view = QtWidgets.QPlainTextEdit(text)
        view.setReadOnly(True)
        view.setStyleSheet('font-family: "Menlo", "Consolas", monospace; font-size: 11px;')
        self.layout_.addWidget(view, 1)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        close = QtWidgets.QPushButton("CLOSE")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        self.layout_.addLayout(row)


def show_report(report, extra=""):
    exec_dialog(ReportDialog(report, extra))
