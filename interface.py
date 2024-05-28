from PySide6 import QtCore, QtWidgets, QtGui

class QWrapLayout(QtWidgets.QLayout):
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
        return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QtCore.QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super(QWrapLayout, self).setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()

        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())

        size += QtCore.QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0

        for item in self.itemList:
            wid = item.widget()

            spaceX = self.spacing() + self.contentsMargins().left() + self.contentsMargins().right()
            spaceY = self.spacing() + self.contentsMargins().top() + self.contentsMargins().bottom()
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()

class MainWindow(QtWidgets.QWidget):
    def __init__(self, items, button_size=QtCore.QSize(100, 100)):
        super().__init__()

        # Store button size as an instance variable
        self.button_size = button_size

        # Create layout
        layout = QtWidgets.QVBoxLayout(self)

        # Create search bar
        self.search_bar = QtWidgets.QLineEdit(self)
        self.search_bar.setPlaceholderText("Search...")
        layout.addWidget(self.search_bar)

        # Create scroll area
        self.scroll_area = QtWidgets.QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area)

        # Create widget to hold the buttons
        self.scroll_widget = QtWidgets.QWidget(self)
        self.wrap_layout = QWrapLayout(self.scroll_widget)

        # Create buttons based on items list
        self.buttons = []
        for item in items:
            button = QtWidgets.QToolButton(self.scroll_widget)
            button.setFixedSize(self.button_size)  # Set fixed size for button
            button.setIcon(QtGui.QIcon("G:/Chan/Documents/.GITHUB/FiveHub/test/asset/duck.gif"))  # Set the icon
            button.setIconSize(QtCore.QSize(80, 80))  # Set the icon size
            button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)  # Set the text under the icon
            button.setText(item)  # Set the text
            button.clicked.connect(lambda checked, item=item: self.on_button_clicked(item))
            self.wrap_layout.addWidget(button)
            self.buttons.append(button)

        # Set the scroll widget
        self.scroll_area.setWidget(self.scroll_widget)

        # Connect the search bar to the filter function
        self.search_bar.textChanged.connect(self.filter_buttons)

        self.setWindowTitle("Searchable Box List")
        self.resize(400, 500)

    def filter_buttons(self):
        search_text = self.search_bar.text().lower()

        # Hide all buttons and remove them from the layout
        while self.wrap_layout.count():
            item = self.wrap_layout.takeAt(0)
            item.widget().hide()

        # Filter buttons, add them to the layout, and show them
        for button in self.buttons:
            button_text = button.text().lower()
            if search_text in button_text:
                self.wrap_layout.addWidget(button)
                button.show()

    def on_button_clicked(self, item):
        print(item)

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)

    # List of items to create buttons for
    items = [f"Box {i}" for i in range(1, 101)]

    main_window = MainWindow(items)
    main_window.show()

    sys.exit(app.exec())