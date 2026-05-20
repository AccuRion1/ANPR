import sys
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QMessageBox,
)

from auth.auth_service import authenticate_user
from GUI.qt_main_window import QtMainWindow


class QtLoginWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Авторизация")
        self.setFixedSize(360, 200)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Войдите в систему для продолжения"))

        form = QFormLayout()
        self.login_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        form.addRow("Логин:", self.login_edit)
        form.addRow("Пароль:", self.password_edit)

        layout.addLayout(form)
        login_button = QPushButton("Войти")
        login_button.clicked.connect(self.login)
        layout.addWidget(login_button)

    def login(self):
        username = self.login_edit.text().strip()
        password = self.password_edit.text().strip()
        session_id = authenticate_user(username, password)
        if not session_id:
            QMessageBox.critical(self, "Ошибка", "Неверный логин или пароль")
            return

        self.accept()
        self.main_window = QtMainWindow(session_id)
        self.main_window.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    login = QtLoginWindow()
    login.show()
    sys.exit(app.exec_())
