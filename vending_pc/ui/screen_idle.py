from pathlib import Path
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import QTimer, Qt


class ScreenIdle(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        self._images = sorted(Path("media").glob("*.jpg"))
        self._index  = 0

        self._label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)

        self._timer = QTimer()
        self._timer.timeout.connect(self._next)

    def start(self):
        self._images = sorted(Path("media").glob("*.jpg"))
        self._index  = 0
        self._show_current()
        self._timer.start(5000)

    def _next(self):
        if not self._images:
            return
        self._index = (self._index + 1) % len(self._images)
        self._show_current()

    def _show_current(self):
        if not self._images:
            self._label.setText("VendingBox")
            return
        pix = QPixmap(str(self._images[self._index]))
        self._label.setPixmap(
            pix.scaled(self._label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
        )
