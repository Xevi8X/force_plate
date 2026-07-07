import struct
import serial
import time

from typing import Generator

from modbus_config import ModbusConfig

class ActiveTransducer:

    def __init__(self, config: ModbusConfig = ModbusConfig(), device_id: int = 1):
        self._config = config
        self._device_id = device_id
        self._scale_factor = 1.0
        self._ser: serial.Serial | None = None

    def open(self) -> None:
        self._ser = serial.Serial(
            port=self._config.port,
            baudrate=self._config.baudrate,
            bytesize=self._config.bytesize,
            parity=self._config.parity,
            stopbits=self._config.stopbits,
            timeout=0.1,
        )

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()

    def __enter__(self) -> "ActiveTransducer":
        self.open()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def listen(self) -> Generator[float, None, None]:
        if self._ser is None or not self._ser.is_open:
            raise RuntimeError("Port not open — call open() or use as context manager")

        buf = bytearray()
        while True:
            chunk = self._ser.read(256)
            if chunk:
                buf.extend(chunk)

            while len(buf) >= 5:
                if buf[0] != self._device_id or buf[1] != 0x03:
                    del buf[0]
                    continue

                byte_count = buf[2]
                frame_len = 3 + byte_count + 2

                if len(buf) < frame_len:
                    break

                frame = bytes(buf[:frame_len])
                del buf[:frame_len]

                if not self._check_crc(frame):
                    continue

                data = frame[3:3 + byte_count]
                num_regs = byte_count // 2
                if num_regs < 2:
                    continue

                low  = struct.unpack(">H", data[0:2])[0]
                high = struct.unpack(">H", data[2:4])[0]
                raw  = struct.unpack(">i", struct.pack(">I", (high << 16) | low))[0]
                yield raw * self._scale_factor

    @staticmethod
    def _check_crc(frame: bytes) -> bool:
        crc = 0xFFFF
        for byte in frame[:-2]:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        return crc == (frame[-2] | (frame[-1] << 8))
    
if __name__ == "__main__":
    active_transducer = ActiveTransducer()
    start_mono = time.monotonic()

    with active_transducer:
        for weight in active_transducer.listen():
            time_ms = int((time.monotonic() - start_mono) * 1000)
            print(f"{time_ms} ms: {weight:.2f}")
