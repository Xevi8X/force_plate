from dataclasses import dataclass

@dataclass
class ModbusConfig:
    port: str = "/dev/ttyUSB0"
    baudrate: int = 600000
    bytesize: int = 8
    parity: str = "N"
    stopbits: int = 1
    timeout: float = 1.0