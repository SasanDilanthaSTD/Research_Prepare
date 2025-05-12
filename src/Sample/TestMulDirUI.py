from PyQt5 import QtWidgets

class Window(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.button = QtWidgets.QPushButton('Choose Directories')
        self.button.clicked.connect(self.handleChooseDirectories)
        self.listWidget = QtWidgets.QListWidget()
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.listWidget)
        layout.addWidget(self.button)

    def handleChooseDirectories(self):
        dialog = QtWidgets.QFileDialog(self)
        dialog.setWindowTitle('Choose Directories')
        dialog.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)
        dialog.setFileMode(QtWidgets.QFileDialog.DirectoryOnly)
        for view in dialog.findChildren(
            (QtWidgets.QListView, QtWidgets.QTreeView)):
            if isinstance(view.model(), QtWidgets.QFileSystemModel):
                view.setSelectionMode(
                    QtWidgets.QAbstractItemView.ExtendedSelection)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.listWidget.clear()
            self.listWidget.addItems(dialog.selectedFiles())
        dialog.deleteLater()

if __name__ == '__main__':

    app = QtWidgets.QApplication(['Test'])
    window = Window()
    window.show()
    app.exec_()