import asyncio
from PyQt6.QtWidgets import QMainWindow, QStackedWidget
from PyQt6.QtCore import QTimer
from ui.screen_idle import ScreenIdle
from ui.screen_price import ScreenPrice
from ui.screen_dispense import ScreenDispense


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg   = cfg
        self.q_ui  = asyncio.Queue()

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.screen_idle     = ScreenIdle(cfg)
        self.screen_price    = ScreenPrice(cfg)
        self.screen_dispense = ScreenDispense()

        self.stack.addWidget(self.screen_idle)
        self.stack.addWidget(self.screen_price)
        self.stack.addWidget(self.screen_dispense)

        # Опрос очереди UI каждые 50 мс
        self._timer = QTimer()
        self._timer.timeout.connect(self._process_q)
        self._timer.start(50)

    def _process_q(self):
        while not self.q_ui.empty():
            try:
                cmd = self.q_ui.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._dispatch(cmd)

    def _dispatch(self, cmd: dict):
        name = cmd.get("cmd")
        if name == "SHOW_IDLE":
            self.screen_idle.start()
            self.stack.setCurrentWidget(self.screen_idle)
        elif name == "SHOW_PRICE":
            self.screen_price.show_item(cmd["item"])
            self.stack.setCurrentWidget(self.screen_price)
        elif name == "SHOW_DISPENSE":
            self.screen_dispense.show_dispensing()
            self.stack.setCurrentWidget(self.screen_dispense)
        elif name == "SHOW_SUCCESS":
            self.screen_dispense.show_success()
            self.stack.setCurrentWidget(self.screen_dispense)
        elif name == "SHOW_ERROR":
            self.screen_dispense.show_error()
            self.stack.setCurrentWidget(self.screen_dispense)
        elif name == "UPDATE_AMOUNT":
            self.screen_price.update_amount(cmd.get("amount", 0))
