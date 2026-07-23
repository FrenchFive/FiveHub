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
QDialog { background: #f5f5f7; }
QWidget { background: transparent; color: #0b0b0c;
    font-family: "SF Pro Text", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 12px; }
QLabel { background: transparent; }
QLabel#heading { font-size: 21px; font-weight: 700; }
QLabel#headingFail { font-size: 21px; font-weight: 700; color: #ff3b30; }
QLabel#hint { font-size: 10px; font-weight: 600; letter-spacing: 1px;
    color: #6e6e73; }
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


class ContextWidget(QtWidgets.QWidget):
    """Project / kind / entity / task cascade. When ``editable`` the entity
    and task combos accept new names (created on confirm by the caller)."""

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
            self.entity_combo.setEditable(True)
            self.task_combo.setEditable(True)

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
        if self.editable and current:
            self.entity_combo.setEditText(current)
        self.entity_combo.blockSignals(False)
        self._refresh_tasks()

    def _refresh_tasks(self):
        project = self._project()
        kind = self.kind_combo.currentData()
        entity = self.entity_combo.currentText().strip()
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
            if current:
                self.task_combo.setEditText(current)
        self.task_combo.blockSignals(False)
        self.changed.emit()

    def context(self):
        return {
            "project": self.project_combo.currentText().strip(),
            "kind": self.kind_combo.currentData(),
            "entity": self.entity_combo.currentText().strip(),
            "task": self.task_combo.currentText().strip().lower(),
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
                combo.setEditText(value)


class _BaseDialog(QtWidgets.QDialog):
    def __init__(self, heading, parent=None, heading_object="heading"):
        super(_BaseDialog, self).__init__(parent or hou.qt.mainWindow())
        self.setStyleSheet(STYLE)
        self.setWindowTitle("FIVE HUB")
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

        self.layout_.addWidget(_label("NOTES", "hint"))
        self.notes = QtWidgets.QPlainTextEdit()
        self.notes.setFixedHeight(80)
        self.layout_.addWidget(self.notes)

        self.target_label = _label("", "hint")
        self.layout_.addWidget(self.target_label)

        self.add_buttons("SAVE")
        self.context_widget.changed.connect(self._update_target)
        self.context_widget.set_context(prefill)
        self._update_target()

    def _update_target(self):
        context = self.context_widget.context()
        if not (context["project"] and context["entity"] and context["task"]):
            self.target_label.setText("PICK A PROJECT / ENTITY / TASK")
            return
        version = 1
        try:
            project = get_project(context["project"])
            version = project.next_scene_version(
                context["kind"], context["entity"], context["task"]
            )
        except ValueError:
            pass  # entity or task does not exist yet -> first version
        self.target_label.setText(
            "WILL SAVE  %s"
            % config.scene_file_name(context["entity"], context["task"], version)
        )

    def values(self):
        return self.context_widget.context(), self.notes.toPlainText().strip()


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
            text = "%s   %s   %s" % (
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
    """Define what a publish is before it runs: context, format, name,
    variant and comment."""

    def __init__(self, prefill=None, parent=None):
        super(PublishDialog, self).__init__("PUBLISH", parent)
        self.resize(680, 380)

        self.context_widget = ContextWidget(editable=True)
        self.layout_.addWidget(self.context_widget)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)

        self.name_edit = QtWidgets.QLineEdit()
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

        self.hint_label = _label(
            "USD PUBLISHES RUN FULL VALIDATION — ERRORS BLOCK THE PUBLISH", "hint"
        )
        self.layout_.addWidget(self.hint_label)

        self.add_buttons("VALIDATE + PUBLISH")
        self.context_widget.changed.connect(self._sync_name)
        self.context_widget.set_context(prefill)
        self._sync_name()

    def _sync_name(self):
        entity = self.context_widget.context()["entity"]
        if entity and not self.name_edit.isModified():
            self.name_edit.setText(entity)

    def values(self):
        return {
            "context": self.context_widget.context(),
            "name": self.name_edit.text().strip(),
            "format": self.format_combo.currentData(),
            "variant": self.variant_edit.text().strip() or "default",
            "comment": self.comment_edit.text().strip(),
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
