import asyncio
from enum import Enum, auto
from core.db import Database
from drivers.driver_rs485 import DriverRS485
from drivers.driver_ccnet import DriverCCNet
from drivers.driver_mdb import DriverMDB


class State(Enum):
    IDLE           = auto()
    ITEM_SELECTED  = auto()
    DISPENSING     = auto()
    SUCCESS        = auto()
    ERROR          = auto()


class FSM:
    def __init__(self, cfg: dict, db: Database, q_ui: asyncio.Queue):
        self.cfg    = cfg
        self.db     = db
        self.q_ui   = q_ui
        self.q_in:  asyncio.Queue = asyncio.Queue()

        self.rs485  = DriverRS485(cfg["ports"]["rs485"], self.q_in)
        self.ccnet  = DriverCCNet(cfg["ports"]["ccnet"], self.q_in)
        self.mdb    = DriverMDB(cfg["ports"]["mdb"],   self.q_in)

        self.state        = State.IDLE
        self.selected_item: dict | None = None
        self.paid_amount  = 0
        self.pay_method   = ""
        self._timer_task: asyncio.Task | None = None

    # ------------------------------------------------------------------ #

    async def run(self):
        while True:
            event = await self.q_in.get()
            await self._handle(event)

    async def _handle(self, ev: dict):
        src, name, data = ev["source"], ev["event"], ev["data"]

        if name == "BUTTON_PRESSED":
            await self._on_button(data["addr"])

        elif name == "BILL_ESCROW":
            await self._on_escrow(data["amount"])

        elif name == "BILL_STACKED":
            self.paid_amount += data["amount"]
            self.pay_method = "cash"
            if self.paid_amount >= self.selected_item["price"]:
                await self._start_dispense()

        elif name == "SESSION_BEGIN":
            await self.mdb.vend_request(self.selected_item["price"])

        elif name == "VEND_APPROVED":
            self.paid_amount = data["amount"]
            self.pay_method = "card"
            await self._start_dispense()

        elif name == "VEND_DENIED":
            await self._go_idle()

        elif name == "DISPENSE_OK":
            await self._on_success()

        elif name == "DISPENSE_TIMEOUT":
            await self._on_error()

    # ------------------------------------------------------------------ #

    async def _on_button(self, addr: int):
        item = next((i for i in self.cfg["items"] if i["addr"] == addr), None)
        if not item:
            return
        self.selected_item = item
        self.paid_amount   = 0
        self._reset_timer()

        if self.state == State.IDLE:
            await self.ccnet.enable()
            await self.mdb.start_session()

        self.state = State.ITEM_SELECTED
        await self.q_ui.put({"cmd": "SHOW_PRICE", "item": item})
        self._timer_task = asyncio.create_task(
            self._payment_timeout(self.cfg["timeouts"]["payment_sec"])
        )

    async def _on_escrow(self, amount: int):
        if amount >= self.selected_item["price"]:
            await self.ccnet.stack()
        else:
            await self.ccnet.ret()

    async def _start_dispense(self):
        self._reset_timer()
        self.state = State.DISPENSING
        await self.q_ui.put({"cmd": "SHOW_DISPENSE"})
        await self.rs485.motor_start(
            self.selected_item["addr"],
            self.selected_item["motor_direction"]
        )

    async def _on_success(self):
        self.state = State.SUCCESS
        self.db.save_transaction(
            self.selected_item["addr"], self.selected_item["name"],
            self.selected_item["price"], self.paid_amount,
            self.pay_method, "OK"
        )
        await self.mdb.vend_success()
        await self.ccnet.disable()
        await self.q_ui.put({"cmd": "SHOW_SUCCESS"})
        await asyncio.sleep(self.cfg["timeouts"]["success_screen_sec"])
        await self._go_idle()

    async def _on_error(self):
        self.state = State.ERROR
        self.db.save_transaction(
            self.selected_item["addr"], self.selected_item["name"],
            self.selected_item["price"], self.paid_amount,
            self.pay_method, "ERROR"
        )
        await self.mdb.vend_failure()
        await self.ccnet.ret_all(self.paid_amount)
        await self.q_ui.put({"cmd": "SHOW_ERROR"})
        await asyncio.sleep(3)
        await self._go_idle()

    async def _go_idle(self):
        self._reset_timer()
        self.state         = State.IDLE
        self.selected_item = None
        self.paid_amount   = 0
        await self.ccnet.disable()
        await self.mdb.end_session()
        await self.q_ui.put({"cmd": "SHOW_IDLE"})

    async def _payment_timeout(self, seconds: int):
        await asyncio.sleep(seconds)
        if self.state == State.ITEM_SELECTED:
            await self._go_idle()

    def _reset_timer(self):
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = None
