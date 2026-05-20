import sys
from PyQt5.QtWidgets import QApplication
from GUI.qt_login_window import QtLoginWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    login_window = QtLoginWindow()
    login_window.show()
    sys.exit(app.exec_())