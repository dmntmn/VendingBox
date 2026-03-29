from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt


class ScreenDispense(QWidget):
    def __init__(self):
        super().__init__()
        self._label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("font-size: 48px;")
        QVBoxLayout(self).addWidget(self._label)

    def show_dispensing(self):
        self._label.setText("⏳ Выдача товара...")

    def show_success(self):
        self._label.setText("✅ Заберите товар!")

    def show_error(self):
        self._label.setText("❌ Ошибка выдачи\nДеньги будут возвращены")
