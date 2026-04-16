"""BMS 데이터 수집 - RS485 Modbus RTU (CRC16)

패킷 구조
─────────────────────────────────────────────────────────
[요청 프레임] 8 bytes
  Byte 0   : Slave Address  (1 byte)
  Byte 1   : Function Code  0x03 (Read Holding Registers)
  Byte 2-3 : Start Register (2 bytes, big-endian)
  Byte 4-5 : Register Count (2 bytes, big-endian)
  Byte 6-7 : CRC16          (2 bytes, little-endian)

[응답 프레임] 5 + 2*N bytes
  Byte 0   : Slave Address
  Byte 1   : Function Code  0x03
  Byte 2   : Byte Count     (2 * register_count)
  Byte 3.. : Register Data  (big-endian uint16 per register)
  Last 2   : CRC16          (little-endian)

레지스터 맵 (reg_start 기준 오프셋)
  +0  총 전압        (uint16, ×0.1 V)
  +1  전류           (int16,  ×0.1 A, 음수=충전)
  +2  SOC            (uint16, ×0.1 %)
  +3  셀 최고온도   (int16,  ×0.1 ℃)
  +4  셀 최저온도   (int16,  ×0.1 ℃)
  +5  셀 최고전압   (uint16, ×0.001 V)
  +6  셀 최저전압   (uint16, ×0.001 V)
  +7  방전 사이클수 (uint16, count)
  +8  알람 플래그   (uint16, bitmask)
  +9  보호 플래그   (uint16, bitmask)
─────────────────────────────────────────────────────────
"""

import logging
import struct
from dataclasses import dataclass, field
from typing import Optional

import serial

from collector.collector_config import BmsConfig

logger = logging.getLogger(__name__)


# ── CRC16 (Modbus 표준) ──────────────────────────────────────────────────────

def _crc16(data: bytes) -> int:
    """Modbus CRC16 계산. 반환값: 16-bit unsigned int"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def _append_crc(frame: bytes) -> bytes:
    crc = _crc16(frame)
    return frame + struct.pack("<H", crc)   # little-endian


def _check_crc(frame: bytes) -> bool:
    """마지막 2바이트가 앞 데이터의 CRC16과 일치하는지 검증"""
    if len(frame) < 3:
        return False
    payload, crc_bytes = frame[:-2], frame[-2:]
    expected = _crc16(payload)
    received, = struct.unpack("<H", crc_bytes)
    return expected == received


# ── 요청 프레임 빌더 ─────────────────────────────────────────────────────────

def _build_read_request(slave_id: int, start_reg: int, count: int) -> bytes:
    frame = struct.pack(">BBHH", slave_id, 0x03, start_reg, count)
    return _append_crc(frame)


# ── 데이터 클래스 ────────────────────────────────────────────────────────────

@dataclass
class BmsData:
    voltage_v: float          = 0.0   # 총 전압 (V)
    current_a: float          = 0.0   # 전류 (A, 음수=충전)
    soc_pct: float            = 0.0   # SOC (%)
    cell_temp_max_c: float    = 0.0   # 셀 최고 온도 (℃)
    cell_temp_min_c: float    = 0.0   # 셀 최저 온도 (℃)
    cell_volt_max_v: float    = 0.0   # 셀 최고 전압 (V)
    cell_volt_min_v: float    = 0.0   # 셀 최저 전압 (V)
    cycle_count: int          = 0     # 방전 사이클 수
    alarm_flags: int          = 0     # 알람 플래그
    protect_flags: int        = 0     # 보호 플래그
    ok: bool                  = False # 통신 성공 여부


# ── 메인 리더 ────────────────────────────────────────────────────────────────

class BmsReader:
    """BMS RS485 Modbus RTU 리더"""

    def __init__(self, cfg: BmsConfig):
        self._cfg = cfg
        self._ser: Optional[serial.Serial] = None

    # ── 연결 관리 ────────────────────────────────────────────────────────────

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
        logger.info("[BMS] 포트 열림: %s %dbps", cfg.port, cfg.baudrate)

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
            logger.info("[BMS] 포트 닫힘")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # ── 수집 ─────────────────────────────────────────────────────────────────

    def read(self) -> BmsData:
        cfg = self._cfg
        result = BmsData()
        try:
            req = _build_read_request(cfg.slave_id, cfg.reg_start, cfg.reg_count)
            logger.debug("[BMS] TX: %s", req.hex(" ").upper())

            self._ser.reset_input_buffer()
            self._ser.write(req)

            # 응답 길이: 1(addr)+1(fc)+1(bc)+2*N(data)+2(crc)
            expected_len = 5 + 2 * cfg.reg_count
            resp = self._ser.read(expected_len)

            if len(resp) != expected_len:
                logger.warning("[BMS] 응답 길이 불일치: %d/%d bytes", len(resp), expected_len)
                return result

            logger.debug("[BMS] RX: %s", resp.hex(" ").upper())

            if not _check_crc(resp):
                logger.warning("[BMS] CRC16 오류")
                return result

            # 오류 응답 (FC | 0x80)
            if resp[1] & 0x80:
                logger.warning("[BMS] Modbus 예외 응답: 에러코드 0x%02X", resp[2])
                return result

            regs = _parse_registers(resp, cfg.reg_count)
            result = _decode(regs, cfg.reg_start)
            result.ok = True

        except serial.SerialException as exc:
            logger.error("[BMS] 시리얼 오류: %s", exc)
        except Exception as exc:
            logger.error("[BMS] 예외: %s", exc)

        return result


# ── 파싱 헬퍼 ────────────────────────────────────────────────────────────────

def _parse_registers(resp: bytes, count: int) -> list[int]:
    """응답 바이트에서 uint16 레지스터 리스트 추출 (big-endian)"""
    data = resp[3: 3 + 2 * count]
    return list(struct.unpack(f">{count}H", data))


def _s16(val: int) -> int:
    """uint16 → signed int16"""
    return val if val < 0x8000 else val - 0x10000


def _decode(regs: list[int], base: int) -> BmsData:
    d = BmsData()
    if len(regs) < 10:
        return d
    d.voltage_v       = regs[0] * 0.1
    d.current_a       = _s16(regs[1]) * 0.1
    d.soc_pct         = regs[2] * 0.1
    d.cell_temp_max_c = _s16(regs[3]) * 0.1
    d.cell_temp_min_c = _s16(regs[4]) * 0.1
    d.cell_volt_max_v = regs[5] * 0.001
    d.cell_volt_min_v = regs[6] * 0.001
    d.cycle_count     = regs[7]
    d.alarm_flags     = regs[8]
    d.protect_flags   = regs[9]
    return d
