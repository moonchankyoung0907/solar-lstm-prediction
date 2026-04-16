"""기상센서 데이터 수집 - UART 17byte 고정 패킷, XOR 체크섬

패킷 구조 (17 bytes)
─────────────────────────────────────────────────────────
Byte  0    : 헤더1       0xAA
Byte  1    : 헤더2       0x55
Byte  2    : 장치 ID     (uint8)
Byte  3-4  : 일사량      (uint16 BE, ×0.1 W/m²)
Byte  5-6  : 기온        (int16  BE, ×0.1 ℃)
Byte  7-8  : 풍속        (uint16 BE, ×0.1 m/s)
Byte  9-10 : 풍향        (uint16 BE, 0~3599 → ×0.1 °)
Byte 11-12 : 상대습도    (uint16 BE, ×0.1 %)
Byte 13-14 : 기압        (uint16 BE, ×0.1 hPa)
Byte 15    : 상태 플래그 (uint8, bit0=일사량이상, bit1=온도이상)
Byte 16    : XOR 체크섬  (XOR of bytes 0~15)
─────────────────────────────────────────────────────────
"""

import logging
import struct
from dataclasses import dataclass
from typing import Optional

import serial

from collector.collector_config import WeatherConfig

logger = logging.getLogger(__name__)


# ── XOR 체크섬 ───────────────────────────────────────────────────────────────

def _xor_checksum(data: bytes) -> int:
    result = 0
    for b in data:
        result ^= b
    return result


def _check_xor(packet: bytes) -> bool:
    """마지막 바이트가 앞 N-1 바이트의 XOR과 일치하는지 검증"""
    return _xor_checksum(packet[:-1]) == packet[-1]


# ── 데이터 클래스 ────────────────────────────────────────────────────────────

@dataclass
class WeatherData:
    device_id: int      = 0
    irradiance_wm2: float  = 0.0   # 일사량 (W/m²)
    temperature_c: float   = 0.0   # 기온 (℃)
    wind_speed_ms: float   = 0.0   # 풍속 (m/s)
    wind_dir_deg: float    = 0.0   # 풍향 (°)
    humidity_pct: float    = 0.0   # 상대습도 (%)
    pressure_hpa: float    = 0.0   # 기압 (hPa)
    status: int            = 0     # 상태 플래그
    ok: bool               = False


# ── 메인 리더 ────────────────────────────────────────────────────────────────

class WeatherReader:
    """기상센서 UART 17byte 리더"""

    def __init__(self, cfg: WeatherConfig):
        self._cfg = cfg
        self._ser: Optional[serial.Serial] = None

    def open(self) -> None:
        cfg = self._cfg
        self._ser = serial.Serial(
            port=cfg.port,
            baudrate=cfg.baudrate,
            bytesize=cfg.bytesize,
            parity=cfg.parity,
            stopbits=cfg.stopbits,
            timeout=cfg.timeout,
        )
        logger.info("[Weather] 포트 열림: %s %dbps", cfg.port, cfg.baudrate)

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
            logger.info("[Weather] 포트 닫힘")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # ── 수집 ─────────────────────────────────────────────────────────────────

    def read(self) -> WeatherData:
        cfg = self._cfg
        result = WeatherData()
        try:
            packet = self._read_packet()
            if packet is None:
                return result

            logger.debug("[Weather] RX: %s", packet.hex(" ").upper())

            if not _check_xor(packet):
                logger.warning("[Weather] XOR 체크섬 오류")
                return result

            result = _decode(packet)
            result.ok = True

        except serial.SerialException as exc:
            logger.error("[Weather] 시리얼 오류: %s", exc)
        except Exception as exc:
            logger.error("[Weather] 예외: %s", exc)

        return result

    def _read_packet(self) -> Optional[bytes]:
        """헤더(0xAA 0x55)를 찾아 17바이트 패킷을 수신"""
        cfg = self._cfg
        h0, h1 = cfg.header_b0, cfg.header_b1
        plen = cfg.packet_len

        # 헤더 동기화 (최대 plen*2 바이트 탐색)
        buf = bytearray()
        for _ in range(plen * 2):
            b = self._ser.read(1)
            if not b:
                logger.warning("[Weather] 수신 타임아웃")
                return None
            buf.append(b[0])

            # 헤더 발견
            if len(buf) >= 2 and buf[-2] == h0 and buf[-1] == h1:
                # 헤더 2바이트는 이미 수신됨, 나머지 읽기
                remain = self._ser.read(plen - 2)
                if len(remain) != plen - 2:
                    logger.warning("[Weather] 패킷 길이 부족: %d bytes", 2 + len(remain))
                    return None
                packet = bytes([h0, h1]) + remain
                return packet

        logger.warning("[Weather] 헤더(0x%02X 0x%02X)를 찾지 못함", h0, h1)
        return None


# ── 파싱 ─────────────────────────────────────────────────────────────────────

def _s16(val: int) -> int:
    return val if val < 0x8000 else val - 0x10000


def _decode(pkt: bytes) -> WeatherData:
    d = WeatherData()
    # struct: skip header(2) + device_id(1) + 6×uint16 + status(1) + xor(1)
    device_id                   = pkt[2]
    irr, temp_raw, wspd, wdir, hum, pres = struct.unpack(">HHHHHH", pkt[3:15])
    status                      = pkt[15]

    d.device_id      = device_id
    d.irradiance_wm2 = irr  * 0.1
    d.temperature_c  = _s16(temp_raw) * 0.1
    d.wind_speed_ms  = wspd * 0.1
    d.wind_dir_deg   = wdir * 0.1
    d.humidity_pct   = hum  * 0.1
    d.pressure_hpa   = pres * 0.1
    d.status         = status
    return d
