import hou
from PySide2.QtWidgets import QDialog, QPushButton, QVBoxLayout, QWidget, QLineEdit, QLabel
from PySide2.QtCore import Qt

class AddWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle('Add Window')
        self.resize(250, 150)

        self.name_label = QLabel("Enter your name:")
        self.name_input = QLineEdit()

        self.project_label = QLabel("Enter your project name:")
        self.project_input = QLineEdit()

        self.confirm_button = QPushButton("Confirm")
        self.confirm_button.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(self.name_label)
        layout.addWidget(self.name_input)
        layout.addWidget(self.project_label)
        layout.addWidget(self.project_input)
        layout.addWidget(self.confirm_button)

        self.setLayout(layout)

    def accept(self):
        self.name = self.name_input.text()
        self.project = self.project_input.text()
        super().accept()

    def get_inputs(self):
        return self.name, self.project
    

def addwindow():
    dialog = AddWindow(hou.qt.mainWindow())
    dialog.exec_()
    return dialog.get_inputs()

