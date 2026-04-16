"""config.ini 로더 - 수집기 설정 파싱"""

import configparser
import pathlib

_INI = pathlib.Path(__file__).parent / "config.ini"


def _read() -> configparser.ConfigParser:
    cp = configparser.ConfigParser()
    cp.read(_INI, encoding="utf-8")
    return cp


def _hex(val: str) -> int:
    return int(val, 16) if val.startswith("0x") or val.startswith("0X") else int(val)


class BmsConfig:
    def __init__(self, cp: configparser.ConfigParser):
        s = cp["bms"]
        self.port      = s["port"]
        self.baudrate  = int(s["baudrate"])
        self.bytesize  = int(s["bytesize"])
        self.parity    = s["parity"]
        self.stopbits  = int(s["stopbits"])
        self.timeout   = float(s["timeout"])
        self.slave_id  = _hex(s["slave_id"])
        self.reg_start = _hex(s["reg_start"])
        self.reg_count = int(s["reg_count"])


class WeatherConfig:
    def __init__(self, cp: configparser.ConfigParser):
        s = cp["weather"]
        self.port       = s["port"]
        self.baudrate   = int(s["baudrate"])
        self.bytesize   = int(s["bytesize"])
        self.parity     = s["parity"]
        self.stopbits   = int(s["stopbits"])
        self.timeout    = float(s["timeout"])
        self.header_b0  = _hex(s["header_b0"])
        self.header_b1  = _hex(s["header_b1"])
        self.packet_len = int(s["packet_len"])


class MeterConfig:
    def __init__(self, cp: configparser.ConfigParser):
        s = cp["meter"]
        self.port       = s["port"]
        self.baudrate   = int(s["baudrate"])
        self.bytesize   = int(s["bytesize"])
        self.parity     = s["parity"]
        self.stopbits   = int(s["stopbits"])
        self.timeout    = float(s["timeout"])
        self.start_byte = _hex(s["start_byte"])
        self.end_byte   = _hex(s["end_byte"])
        self.packet_len = int(s["packet_len"])


class CollectorConfig:
    def __init__(self, cp: configparser.ConfigParser):
        s = cp["collector"]
        self.interval_sec = int(s["interval_sec"])
        self.xlsx_path    = pathlib.Path(__file__).parent / s["xlsx_path"]
        self.log_level    = s.get("log_level", "INFO").upper()


def load() -> tuple[BmsConfig, WeatherConfig, MeterConfig, CollectorConfig]:
    cp = _read()
    return BmsConfig(cp), WeatherConfig(cp), MeterConfig(cp), CollectorConfig(cp)
