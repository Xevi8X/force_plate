import struct

from enum import IntEnum
from pymodbus.client import ModbusSerialClient

from .modbus_config import ModbusConfig

class Register(IntEnum):
    # Total weight (32-bit signed, low/high word pair)
    TOTAL_WEIGHT_LOW            = 0x0000
    TOTAL_WEIGHT_HIGH           = 0x0001
    # Net weight (32-bit signed)
    NET_WEIGHT_LOW              = 0x0002
    NET_WEIGHT_HIGH             = 0x0003
    # Peak (32-bit signed)
    PEAK_LOW                    = 0x0004
    PEAK_HIGH                   = 0x0005
    # Internal ADC code value (32-bit signed)
    INTERNAL_CODE_LOW           = 0x0006
    INTERNAL_CODE_HIGH          = 0x0007
    # Decimal point position (0-4)
    DECIMAL_POINT               = 0x0008
    # Unit (0=none,1=g,2=kg,3=t,4=N,5=pa,6=kpa,7=mpa,8=N.M,9=kN)
    UNIT                        = 0x0009
    # Device state flags
    STATE                       = 0x000A
    # Command register (write to trigger tare/zero/calibrate etc.)
    ORDER                       = 0x000B
    # Calibration weight value (32-bit unsigned)
    WEIGHT_VALUE_LOW            = 0x000C
    WEIGHT_VALUE_HIGH           = 0x000D
    # Creep tracking level (0-10)
    CREEP_TRACKING              = 0x000E
    # Display zeroing range
    DISPLAY_ZERO_RANGE          = 0x000F
    # Dynamic tracking range
    DYNAMIC_TRACKING_RANGE      = 0x0010
    # Dynamic tracking update interval (ms)
    DYNAMIC_TRACKING_REFRESH    = 0x0011
    # Stabilizing weight switch (0=off, 1=on)
    STABILIZING_WEIGHT_SWITCH   = 0x0012
    # Zero range
    ZERO_RANGE                  = 0x0013
    # Power-on auto-zero switch (0=off, 1=on)
    POWER_ON_ZERO_SWITCH        = 0x0014
    # Power-on auto-zero countdown time (s)
    POWER_ON_ZERO_TIME          = 0x0015
    # Power-on auto-zero range
    POWER_ON_ZERO_RANGE         = 0x0016
    # Automatic zeroing enable (0=off, 1=on)
    AUTO_ZERO_ENABLE            = 0x0017
    # Automatic zeroing time (ms)
    AUTO_ZERO_TIME              = 0x0018
    # Automatic zeroing range (unit 0.1)
    AUTO_ZERO_RANGE             = 0x0019
    # Weight stability judgement range (index)
    STABILITY_RANGE             = 0x001A
    # Weight stability judgement time (ms)
    STABILITY_TIME              = 0x001B
    # Relay 1
    RELAY1_MODE                 = 0x001C
    RELAY1_HYSTERESIS           = 0x001D
    RELAY1_DATA_TYPE            = 0x001E
    RELAY1_ACTION_DELAY         = 0x001F
    RELAY1_UPPER_LIMIT_LOW      = 0x0020
    RELAY1_UPPER_LIMIT_HIGH     = 0x0021
    RELAY1_LOWER_LIMIT_LOW      = 0x0022
    RELAY1_LOWER_LIMIT_HIGH     = 0x0023
    # Relay 2
    RELAY2_MODE                 = 0x0024
    RELAY2_HYSTERESIS           = 0x0025
    RELAY2_DATA_TYPE            = 0x0026
    RELAY2_ACTION_DELAY         = 0x0027
    RELAY2_UPPER_LIMIT_LOW      = 0x0028
    RELAY2_UPPER_LIMIT_HIGH     = 0x0029
    RELAY2_LOWER_LIMIT_LOW      = 0x002A
    RELAY2_LOWER_LIMIT_HIGH     = 0x002B
    # Relay 3
    RELAY3_MODE                 = 0x002C
    RELAY3_HYSTERESIS           = 0x002D
    RELAY3_DATA_TYPE            = 0x002E
    RELAY3_ACTION_DELAY         = 0x002F
    RELAY3_UPPER_LIMIT_LOW      = 0x0030
    RELAY3_UPPER_LIMIT_HIGH     = 0x0031
    RELAY3_LOWER_LIMIT_LOW      = 0x0032
    RELAY3_LOWER_LIMIT_HIGH     = 0x0033
    # Firmware / calibration info
    SOFTWARE_VERSION            = 0x0034
    CALIBRATION_MODE            = 0x0035
    SENSOR_RANGE_LOW            = 0x0036
    SENSOR_RANGE_HIGH           = 0x0037
    SENSOR_SENSITIVITY_LOW      = 0x0038
    SENSOR_SENSITIVITY_HIGH     = 0x0039
    SENSOR_EXCITATION_LOW       = 0x003A
    SENSOR_EXCITATION_HIGH      = 0x003B
    RANGE_COEFFICIENT_LOW       = 0x003C
    RANGE_COEFFICIENT_HIGH      = 0x003D
    DEVICE_UNIQUE_CODE          = 0x003E


class TransducerException(Exception):
    pass

class Transducer:
    def __init__(self, config: ModbusConfig = ModbusConfig(), device_id: int = 1):
        self._config = config
        self._modbus_client = ModbusSerialClient(
            port=self._config.port,
            baudrate=self._config.baudrate,
            bytesize=self._config.bytesize,
            parity=self._config.parity,
            stopbits=self._config.stopbits,
            timeout=self._config.timeout,
        )
        self._device_id : int = device_id
        self._scale_factor : float = 1.0

        if not self._modbus_client.connect():
            raise TransducerException(f"Failed to connect to {self._config.port}")
        
        # Default paramters
        self._write_uint16(Register.DECIMAL_POINT, 0)
        self._write_uint16(Register.DISPLAY_ZERO_RANGE, 0)
        self._write_uint16(Register.UNIT, 0)
        self._write_uint16(Register.CREEP_TRACKING, 0)
        self._write_uint16(Register.STABILIZING_WEIGHT_SWITCH, 0)
        self._write_uint16(Register.AUTO_ZERO_ENABLE, 0)

    def read_weight(self) -> float:
        raw_weight = self._read_int32(Register.TOTAL_WEIGHT_LOW)
        weight = raw_weight * self._scale_factor
        return weight
    
    def read_device_unique_code(self) -> int:
        return self._read_uint16(Register.DEVICE_UNIQUE_CODE)
    
    def zero_weight(self) -> None:
        self._write_uint16(Register.ORDER, 5)

    def set_weight(self, weight: int) -> None:
        if weight < 0 or weight > 4294967295:
            raise ValueError("Weight must be a 32-bit unsigned integer")

        self._write_uint16(Register.CALIBRATION_MODE, 0)
        self._write_uint32(Register.WEIGHT_VALUE_LOW, weight)
        self._write_uint16(Register.ORDER, 7, no_response_expected=True)
    
    def _read_uint16(self, address: int) -> int:
        result = self._modbus_client.read_holding_registers(address=address, count=1, device_id=self._device_id)
        if result.isError():
            raise TransducerException(f"Modbus error reading register {address}: {result}")
        return result.registers[0]
    
    def _read_int16(self, address: int) -> int:
        value = self._read_uint16(address)
        return struct.unpack(">h", struct.pack(">H", value))[0]
    
    def _read_uint32(self, address: int) -> int:
        result = self._modbus_client.read_holding_registers(address=address, count=2, device_id=self._device_id)
        if result.isError():
            raise TransducerException(f"Modbus error reading registers {address}-{address+1}: {result}")
        return (result.registers[1] << 16) | result.registers[0]
    
    def _read_int32(self, address: int) -> int:
        value = self._read_uint32(address)
        return struct.unpack(">i", struct.pack(">I", value))[0]
    
    def _write_uint16(self, address: int, value: int, no_response_expected: bool = False) -> None:
        if not (0 <= value <= 65535):
            raise ValueError("Value must be a 16-bit unsigned integer")
        result = self._modbus_client.write_register(address=address, value=value, device_id=self._device_id, no_response_expected=no_response_expected)
        if not no_response_expected and result.isError():
            raise TransducerException(f"Modbus error writing register {address}: {result}")
    
    def _write_int16(self, address: int, value: int, no_response_expected: bool = False) -> None:
        if not (-32768 <= value <= 32767):
            raise ValueError("Value must be a 16-bit signed integer")
        result = self._modbus_client.write_register(address=address, value=value, device_id=self._device_id, no_response_expected=no_response_expected)
        if not no_response_expected and result.isError():
            raise TransducerException(f"Modbus error writing register {address}: {result}")
        
    def _write_uint32(self, address: int, value: int, no_response_expected: bool = False) -> None:
        if not (0 <= value <= 4294967295):
            raise ValueError("Value must be a 32-bit unsigned integer")
        low_word = value & 0xFFFF
        high_word = (value >> 16) & 0xFFFF
        result = self._modbus_client.write_registers(address=address, values=[low_word, high_word], device_id=self._device_id, no_response_expected=no_response_expected)
        if not no_response_expected and result.isError():
            raise TransducerException(f"Modbus error writing registers {address}-{address+1}: {result}")
    
    def _write_int32(self, address: int, value: int, no_response_expected: bool = False) -> None:
        if not (-2147483648 <= value <= 2147483647):
            raise ValueError("Value must be a 32-bit signed integer")
        low_word = value & 0xFFFF
        high_word = (value >> 16) & 0xFFFF
        result = self._modbus_client.write_registers(address=address, values=[low_word, high_word], device_id=self._device_id, no_response_expected=no_response_expected)
        if not no_response_expected and result.isError():
            raise TransducerException(f"Modbus error writing registers {address}-{address+1}: {result}")
        
if __name__ == "__main__":
    transducer = Transducer()
