import asyncio
import qasync
from PyQt6.QtWidgets import QApplication
from core.config_loader import load_config
from core.db import Database
from core.fsm import FSM
from ui.main_window import MainWindow


async def main(fsm: FSM):
    await asyncio.gather(
        fsm.run(),
        fsm.rs485.run(),
        fsm.ccnet.run(),
        fsm.mdb.run(),
    )


if __name__ == "__main__":
    cfg = load_config("config.json")
    db = Database("vending.db")

    app = QApplication([])
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow(cfg)
    window.showFullScreen()

    fsm = FSM(cfg, db, window.q_ui)

    with loop:
        loop.run_until_complete(main(fsm))
