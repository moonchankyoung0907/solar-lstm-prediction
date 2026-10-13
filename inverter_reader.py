"""
DASS DSP-123K7C-OD 인버터 - Modbus 스타일(func 0x09) 1회 폴링 모듈

collector.py에서 import해서 쓴다. RealTerm/다른 프로그램이 COM4를 점유 중이면
포트 오픈에 실패하므로 comm_status에 에러를 담아 반환하고 예외를 던지지 않는다
(날씨 데이터 수집은 인버터 상태와 무관하게 계속 진행돼야 하므로).

응답 프레임 구조(실측으로 확인됨): [요청 echo 6바이트] + [데이터, 워드당 2바이트 low-byte-first] + [CRC16 low,high]
"""

import time

import serial

PORT = "COM4"
BAUDRATE = 9600
SLAVE_ID = 0x01
FUNC_READ = 0x09
READ_TIMEOUT = 0.3
INTER_REQUEST_DELAY = 0.2

# 주소 -> (필드명, 워드수, signed 여부, SF(10**sf 배율), 단위)
REGISTER_MAP = [
    (0x100B, "grid_voltage_v",        1, False, -1),
    (0x2409, "pv1_current_a",         1, False, -1),
    (0x240A, "pv2_current_a",         1, False, -1),
    (0x240B, "pv3_current_a",         1, False, -1),
    (0x240C, "pv4_voltage_v",         1, False, -1),
    (0x240F, "pv4_current_a",         1, False, -1),
    (0x2704, "cumulative_energy_kwh", 2, False,  0),
]

FIELDS = [f for _, f, *_ in REGISTER_MAP]


def _modbus_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc


def _build_request(addr: int, qty: int) -> bytes:
    body = bytes([
        SLAVE_ID, FUNC_READ,
        addr & 0xFF, (addr >> 8) & 0xFF,
        qty & 0xFF, (qty >> 8) & 0xFF,
    ])
    crc = _modbus_crc16(body)
    return body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def _decode(resp: bytes, words: int, signed: bool, sf: int):
    if len(resp) < 3:
        return None
    payload, recv_crc_bytes = resp[:-2], resp[-2:]
    recv_crc = recv_crc_bytes[0] | (recv_crc_bytes[1] << 8)
    if _modbus_crc16(payload) != recv_crc:
        return None
    data_len = words * 2
    header_len = len(payload) - data_len
    if header_len < 0:
        return None
    data_bytes = payload[header_len:]
    val = int.from_bytes(data_bytes, byteorder="little", signed=signed)
    return val * (10 ** sf)


def read_inverter_once(port: str = PORT) -> dict:
    """레지스터 전부를 1회씩 폴링해서 dict로 반환. 실패한 필드는 None.
    반환 dict에는 FIELDS의 각 값 + 'comm_status' 키가 들어간다."""
    result = {f: None for f in FIELDS}

    try:
        ser = serial.Serial(
            port=port, baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE, timeout=READ_TIMEOUT,
        )
    except serial.SerialException as e:
        result["comm_status"] = f"PORT_ERROR: {e}"
        return result

    ok_count = 0
    try:
        for addr, field, words, signed, sf in REGISTER_MAP:
            req = _build_request(addr, words)
            ser.reset_input_buffer()
            ser.write(req)
            ser.flush()
            time.sleep(READ_TIMEOUT)
            n = ser.in_waiting
            resp = ser.read(n) if n else b""
            value = _decode(resp, words, signed, sf) if resp else None
            result[field] = value
            if value is not None:
                ok_count += 1
            time.sleep(INTER_REQUEST_DELAY)
    finally:
        ser.close()

    if ok_count == len(FIELDS):
        result["comm_status"] = "OK"
    elif ok_count == 0:
        result["comm_status"] = "NO_RESPONSE"
    else:
        result["comm_status"] = f"PARTIAL ({ok_count}/{len(FIELDS)})"

    return result


if __name__ == "__main__":
    print(read_inverter_once())
