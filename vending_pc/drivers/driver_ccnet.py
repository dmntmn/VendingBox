import asyncio
import serial_asyncio

BAUD = 9600

# CC-Net команды (упрощённый subset)
CMD_ENABLE  = bytes([0x02, 0x08, 0x10, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F])
CMD_DISABLE = bytes([0x02, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
CMD_STACK   = bytes([0x02, 0x04, 0x02])
CMD_RETURN  = bytes([0x02, 0x04, 0x03])
CMD_POLL    = bytes([0x02, 0x02])

# Статусы ответа
STATUS_ESCROW  = 0x80
STATUS_STACKED = 0x81
STATUS_RETURN  = 0x82

BILL_VALUES = {0x01: 10, 0x02: 50, 0x03: 100, 0x04: 200, 0x05: 500, 0x06: 1000}


class DriverCCNet:
    def __init__(self, port: str, q_in: asyncio.Queue):
        self.port    = port
        self.q_in    = q_in
        self._active = False
        self._reader = self._writer = None

    async def run(self):
        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self.port, baudrate=BAUD
        )
        while True:
            if self._active:
                await self._poll()
            await asyncio.sleep(0.2)

    async def _poll(self):
        self._writer.write(CMD_POLL)
        try:
            raw = await asyncio.wait_for(self._reader.read(16), 0.3)
        except asyncio.TimeoutError:
            return
        if not raw:
            return
        status = raw[0] if raw else None
        if status == STATUS_ESCROW:
            amount = BILL_VALUES.get(raw[1], 0)
            await self.q_in.put({"source": "ccnet", "event": "BILL_ESCROW", "data": {"amount": amount}})
        elif status == STATUS_STACKED:
            amount = BILL_VALUES.get(raw[1], 0)
            await self.q_in.put({"source": "ccnet", "event": "BILL_STACKED", "data": {"amount": amount}})
        elif status == STATUS_RETURN:
            await self.q_in.put({"source": "ccnet", "event": "BILL_RETURNED", "data": {}})

    async def enable(self):
        self._active = True
        if self._writer:
            self._writer.write(CMD_ENABLE)

    async def disable(self):
        self._active = False
        if self._writer:
            self._writer.write(CMD_DISABLE)

    async def stack(self):
        if self._writer:
            self._writer.write(CMD_STACK)

    async def ret(self):
        if self._writer:
            self._writer.write(CMD_RETURN)

    async def ret_all(self, _amount: int):
        await self.ret()
