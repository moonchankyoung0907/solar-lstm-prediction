"""전력량계 데이터 수집 - 4800bps, 8byte 고정 패킷

패킷 구조 (8 bytes)
─────────────────────────────────────────────────────────
Byte 0    : 시작 바이트  0x68
Byte 1    : 장치 주소    (uint8)
Byte 2-3  : 유효 전력    (uint16 BE, ×0.01 kW)
Byte 4-5  : 누적 전력량  (uint16 BE, ×0.1 kWh)
Byte 6    : 체크섬       (Byte 1~5 의 합산 하위 1바이트)
Byte 7    : 종료 바이트  0x16
─────────────────────────────────────────────────────────

체크섬 계산: sum(bytes[1:6]) & 0xFF
"""

import logging
import struct
from dataclasses import dataclass
from typing import Optional

import serial

from collector.collector_config import MeterConfig

logger = logging.getLogger(__name__)

_PACKET_LEN = 8


# ── 체크섬 ───────────────────────────────────────────────────────────────────

def _checksum(pkt: bytes) -> int:
    """Byte 1~5 의 합산 하위 1바이트"""
    return sum(pkt[1:6]) & 0xFF


def _check_packet(pkt: bytes, start_byte: int, end_byte: int) -> bool:
    if len(pkt) != _PACKET_LEN:
        return False
    if pkt[0] != start_byte:
        logger.warning("[Meter] 시작 바이트 불일치: 0x%02X (기대: 0x%02X)", pkt[0], start_byte)
        return False
    if pkt[7] != end_byte:
        logger.warning("[Meter] 종료 바이트 불일치: 0x%02X (기대: 0x%02X)", pkt[7], end_byte)
        return False
    expected_cs = _checksum(pkt)
    if pkt[6] != expected_cs:
        logger.warning("[Meter] 체크섬 오류: 수신 0x%02X / 계산 0x%02X", pkt[6], expected_cs)
        return False
    return True


# ── 데이터 클래스 ────────────────────────────────────────────────────────────

@dataclass
class MeterData:
    device_addr: int      = 0
    power_kw: float       = 0.0   # 유효 전력 (kW)
    energy_kwh: float     = 0.0   # 누적 전력량 (kWh)
    ok: bool              = False


# ── 메인 리더 ────────────────────────────────────────────────────────────────

class MeterReader:
    """전력량계 4800bps 8byte 리더"""

    def __init__(self, cfg: MeterConfig):
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
        logger.info("[Meter] 포트 열림: %s %dbps", cfg.port, cfg.baudrate)

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
            logger.info("[Meter] 포트 닫힘")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # ── 수집 ─────────────────────────────────────────────────────────────────

    def read(self) -> MeterData:
        cfg = self._cfg
        result = MeterData()
        try:
            packet = self._read_packet()
            if packet is None:
                return result

            logger.debug("[Meter] RX: %s", packet.hex(" ").upper())

            if not _check_packet(packet, cfg.start_byte, cfg.end_byte):
                return result

            result = _decode(packet)
            result.ok = True

        except serial.SerialException as exc:
            logger.error("[Meter] 시리얼 오류: %s", exc)
        except Exception as exc:
            logger.error("[Meter] 예외: %s", exc)

        return result

    def _read_packet(self) -> Optional[bytes]:
        """시작 바이트(0x68)를 찾아 8바이트 패킷 수신"""
        cfg = self._cfg
        plen = cfg.packet_len
        start = cfg.start_byte

        # 시작 바이트 동기화 (최대 plen*2 바이트 탐색)
        for _ in range(plen * 2):
            b = self._ser.read(1)
            if not b:
                logger.warning("[Meter] 수신 타임아웃")
                return None
            if b[0] == start:
                remain = self._ser.read(plen - 1)
                if len(remain) != plen - 1:
                    logger.warning("[Meter] 패킷 길이 부족: %d bytes", 1 + len(remain))
                    return None
                return bytes([start]) + remain

        logger.warning("[Meter] 시작 바이트(0x%02X)를 찾지 못함", start)
        return None


# ── 파싱 ─────────────────────────────────────────────────────────────────────

def _decode(pkt: bytes) -> MeterData:
    d = MeterData()
    d.device_addr = pkt[1]
    power_raw,    = struct.unpack(">H", pkt[2:4])
    energy_raw,   = struct.unpack(">H", pkt[4:6])
    d.power_kw    = power_raw  * 0.01
    d.energy_kwh  = energy_raw * 0.1
    return d
