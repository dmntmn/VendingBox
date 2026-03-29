import asyncio
import serial_asyncio

BAUD = 9600

# MDB команды (VMC → периферия)
CMD_RESET    = bytes([0x10])
CMD_SETUP    = bytes([0x11])
CMD_POLL     = bytes([0x12])
CMD_VEND     = bytes([0x13])
CMD_READER   = bytes([0x14])
CMD_EXPANSION = bytes([0x17])

# MDB ответы
ACK          = bytes([0x00])
JUST_RESET   = bytes([0x00])

# Подкоманды VEND
VEND_REQUEST  = 0x00
VEND_CANCEL   = 0x01
VEND_SUCCESS  = 0x02
VEND_FAILURE  = 0x03
SESSION_COMPLETE = 0x04

# Ответы картридера
BEGIN_SESSION = 0x03
VEND_APPROVED = 0x05
VEND_DENIED   = 0x06
END_SESSION   = 0x07


class DriverMDB:
    def __init__(self, port: str, q_in: asyncio.Queue):
        self.port    = port
        self.q_in    = q_in
        self._active = False
        self._reader = self._writer = None

    async def run(self):
        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self.port, baudrate=BAUD
        )
        await self._reset()
        while True:
            if self._active:
                await self._poll()
            await asyncio.sleep(0.1)

    async def _reset(self):
        if self._writer:
            self._writer.write(CMD_RESET)
            await asyncio.sleep(0.5)

    async def _poll(self):
        if not self._writer:
            return
        self._writer.write(CMD_POLL)
        try:
            raw = await asyncio.wait_for(self._reader.read(16), 0.2)
        except asyncio.TimeoutError:
            return
        if not raw:
            return
        resp = raw[0]
        if resp == BEGIN_SESSION:
            await self.q_in.put({"source": "mdb", "event": "SESSION_BEGIN", "data": {}})
        elif resp == VEND_APPROVED:
            amount = int.from_bytes(raw[1:3], "big") if len(raw) >= 3 else 0
            await self.q_in.put({"source": "mdb", "event": "VEND_APPROVED", "data": {"amount": amount}})
        elif resp == VEND_DENIED:
            await self.q_in.put({"source": "mdb", "event": "VEND_DENIED", "data": {}})

    async def start_session(self):
        self._active = True

    async def end_session(self):
        self._active = False
        if self._writer:
            self._writer.write(CMD_VEND + bytes([SESSION_COMPLETE]))

    async def vend_request(self, amount: int):
        if self._writer:
            self._writer.write(CMD_VEND + bytes([VEND_REQUEST]) + amount.to_bytes(2, "big"))

    async def vend_success(self):
        if self._writer:
            self._writer.write(CMD_VEND + bytes([VEND_SUCCESS]))
            await asyncio.sleep(0.1)
            self._writer.write(CMD_VEND + bytes([SESSION_COMPLETE]))
        self._active = False

    async def vend_failure(self):
        if self._writer:
            self._writer.write(CMD_VEND + bytes([VEND_FAILURE]))
            await asyncio.sleep(0.1)
            self._writer.write(CMD_VEND + bytes([SESSION_COMPLETE]))
        self._active = False
