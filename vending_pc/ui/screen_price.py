from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt


class ScreenPrice(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        self._img    = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._name   = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._price  = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._paid   = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        for w in (self._img, self._name, self._price, self._paid):
            layout.addWidget(w)

    def show_item(self, item: dict):
        self._name.setText(item["name"])
        self._price.setText(f"Цена: {item['price']} ₽")
        self._paid.setText("Внесено: 0 ₽")
        pix = QPixmap(item.get("image", ""))
        if not pix.isNull():
            self._img.setPixmap(
                pix.scaled(400, 400, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )

    def update_amount(self, amount: int):
        self._paid.setText(f"Внесено: {amount} ₽")
