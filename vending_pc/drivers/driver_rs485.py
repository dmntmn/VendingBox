import asyncio
import struct
import serial_asyncio
from .crc import crc16

# CMD коды (см. firmware/commands.md)
CMD_GET_STATUS     = 0x02
CMD_MOTOR_START    = 0x03
CMD_MOTOR_STOP     = 0x04
CMD_DISPENSE_RESULT = 0x05

POLL_TIMEOUT   = 0.010   # 10 мс на ответ слейва
BAUD           = 115200
MAX_ADDR       = 32

# Флаги в байте STATUS
FLAG_MOTOR    = 0x01
FLAG_DETECTOR = 0x02
FLAG_BUTTON   = 0x04


def _build_packet(addr: int, cmd: int, data: bytes = b"") -> bytes:
    # [ADDR][LEN][CMD][DATA...][CRC16_LO][CRC16_HI]
    # LEN = 1 (CMD) + len(DATA)
    payload = bytes([addr, 1 + len(data), cmd]) + data
    crc = crc16(payload)
    return payload + struct.pack("<H", crc)


async def _read_packet(reader, timeout: float) -> bytes | None:
    """Читает ровно LEN+4 байт — граница пакета всегда точная."""
    try:
        header = await asyncio.wait_for(reader.readexactly(2), timeout)  # ADDR + LEN
        addr, length = header
        rest = await asyncio.wait_for(reader.readexactly(length + 2), timeout)  # CMD+DATA + CRC
        return header + rest
    except (asyncio.TimeoutError, asyncio.IncompleteReadError):
        return None


def _check_packet(raw: bytes) -> tuple[int, int, bytes] | None:
    if len(raw) < 4:
        return None
    body, crc_bytes = raw[:-2], raw[-2:]
    if struct.pack("<H", crc16(body)) != crc_bytes:
        return None
    # body = [ADDR][LEN][CMD][DATA...]
    return body[0], body[2], body[3:]   # addr, cmd, data


class DriverRS485:
    def __init__(self, port: str, q_in: asyncio.Queue):
        self.port   = port
        self.q_in   = q_in
        self._cmd_q: asyncio.Queue = asyncio.Queue()
        self._reader = self._writer = None

    async def run(self):
        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self.port, baudrate=BAUD
        )
        addr = 1
        while True:
            # Приоритетные команды от FSM (MOTOR_START / STOP)
            while not self._cmd_q.empty():
                pkt = await self._cmd_q.get()
                await self._send(pkt)

            await self._poll_addr(addr)
            addr = addr % MAX_ADDR + 1

    async def _poll_addr(self, addr: int):
        pkt = _build_packet(addr, CMD_GET_STATUS)
        raw = await self._send(pkt)
        if not raw:
            return
        parsed = _check_packet(raw)
        if not parsed:
            return
        _, cmd, data = parsed
        if cmd != CMD_GET_STATUS or not data:
            return
        flags = data[0]
        if flags & FLAG_BUTTON:
            await self.q_in.put({"source": "rs485", "event": "BUTTON_PRESSED", "data": {"addr": addr}})
        if flags & FLAG_DETECTOR:
            await self.q_in.put({"source": "rs485", "event": "DISPENSE_OK", "data": {"addr": addr}})

    async def _send(self, pkt: bytes) -> bytes | None:
        self._writer.write(pkt)
        return await _read_packet(self._reader, POLL_TIMEOUT)

    # Вызывается из FSM
    async def motor_start(self, addr: int, direction: str):
        dir_byte = 0x00 if direction == "forward" else 0x01
        pkt = _build_packet(addr, CMD_MOTOR_START, bytes([dir_byte]))
        await self._cmd_q.put(pkt)

    async def motor_stop(self, addr: int):
        pkt = _build_packet(addr, CMD_MOTOR_STOP)
        await self._cmd_q.put(pkt)
