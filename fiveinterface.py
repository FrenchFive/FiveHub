import hou
from PySide2.QtWidgets import QDialog, QPushButton, QVBoxLayout, QWidget, QLineEdit, QLabel, QScrollArea, QToolButton, QLayout
from PySide2.QtCore import Qt, QRect, QSize, QPoint
from PySide2 import QtGui
from functools import partial
import os


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

class QWrapLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super(QWrapLayout, self).__init__(parent)

        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)

        self.setSpacing(spacing)

        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if index >= 0 and index < len(self.itemList):
            return self.itemList[index]

        return None

    def takeAt(self, index):
        if index >= 0 and index < len(self.itemList):
            return self.itemList.pop(index)

        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super(QWrapLayout, self).setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()

        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())

        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0

        for item in self.itemList:
            spaceX = self.spacing() + self.contentsMargins().left() + self.contentsMargins().right()
            spaceY = self.spacing() + self.contentsMargins().top() + self.contentsMargins().bottom()
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()

class LoadWindow(QDialog):
    def __init__(self, assets, parent=None, button_size=QSize(100, 100)):
        super().__init__(parent)

        self.button_size = button_size

        # Create layout
        layout = QVBoxLayout(self)

        # Create search bar
        self.search_bar = QLineEdit(self)
        self.search_bar.setPlaceholderText("Search...")
        layout.addWidget(self.search_bar)

        self.setWindowTitle('Load Window')
        self.resize(400, 500)

        # Create scroll area
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area)

        # Create widget to hold the buttons
        self.scroll_widget = QWidget(self)
        self.wrap_layout = QWrapLayout(self.scroll_widget)

        # Create buttons based on items list
        self.buttons = []
        for asset in assets:
            id = asset[0]
            name = asset[1]
            button = QToolButton(self.scroll_widget)
            button.setFixedSize(self.button_size)  # Set fixed size for button
            button.setIcon(QtGui.QIcon(f"{os.path.dirname(__file__)}/asset/{id}/{id}.jpg"))  # Set the icon
            button.setIconSize(QSize(80, 80))  # Set the icon size
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)  # Set the text under the icon
            button.setText(name)  # Set the text
            button.clicked.connect(partial(self.on_button_clicked, id))
            self.wrap_layout.addWidget(button)
            self.buttons.append(button)
        
        # Set the scroll widget
        self.scroll_area.setWidget(self.scroll_widget)

        # Connect the search bar to the filter function
        self.search_bar.textChanged.connect(self.filter_buttons)

    def filter_buttons(self):
        search_text = self.search_bar.text().lower()

        # Hide all buttons and remove them from the layout
        while self.wrap_layout.count():
            asset = self.wrap_layout.takeAt(0)
            asset.widget().hide()

        # Filter buttons, add them to the layout, and show them
        for button in self.buttons:
            button_text = button.text().lower()
            if search_text in button_text:
                self.wrap_layout.addWidget(button)
                button.show()

    def on_button_clicked(self, id):
        self.selected_id = id
        self.accept()

    def get_selected_id(self):
        return self.selected_id

def loadwindow(assets):
    dialog = LoadWindow(assets, hou.qt.mainWindow())
    dialog.exec_()
    return dialog.get_selected_id()