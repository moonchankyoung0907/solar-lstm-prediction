"""
vctec P000BDFU / Endeavour Technology PYR20 일사량 센서 - Modbus RTU 1회 폴링 모듈

통신 사양:
    RS485 Modbus RTU, Slave ID 1, 9600-8-N-1
    레지스터 0x0000 = 일사량 (W/m², 직독값), FC03(holding) 우선 / 실패 시 FC04(input) 재시도

설계 원칙은 inverter_reader.py와 동일하다.
포트가 다른 프로그램(RealTerm 등)에 점유돼 있거나 센서가 응답하지 않아도
예외를 던지지 않고 comm_status에 사유를 담아 반환한다.
(일사량 수집 실패가 다른 수집 작업을 중단시키면 안 되므로)
"""

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

# ──────────────────────────────────────────────────────────────
# 현재 사용 중인 포트 - COM4: DASS 인버터 / COM8: WH24 기상센서(웨더게이트)
# COM3: 일사량 센서(vctec P000BDFU / PYR20), SensorOneSet에서 120 W/m² 정상 통신 확인됨
PORT = "COM3"
# ──────────────────────────────────────────────────────────────

BAUDRATE = 9600
BYTESIZE = 8
PARITY = "N"
STOPBITS = 1
SLAVE_ID = 1
TIMEOUT = 1.0
RETRIES = 2

# 일사량 레지스터 주소 및 개수
REG_ADDRESS = 0x0000
REG_COUNT = 1

# 직독값(W/m²)이므로 배율 1.0.
# 만약 실측에서 표시값의 10배로 읽히면 0.1로 바꾸면 된다.
SCALE = 1.0

# 정상 범위 밖의 값은 통신 오류/오결선으로 보고 걸러낸다.
# (지표면 최대 일사량은 맑은 날 정오 기준 약 1000~1200 W/m²)
VALID_MIN = 0.0
VALID_MAX = 2000.0

FIELDS = ["solar_radiation_wm2"]


def read_solar_once(port: str = None, slave_id: int = SLAVE_ID) -> dict:
    """일사량 레지스터를 1회 읽어 dict로 반환한다. 실패 시 값은 None.

    반환: {"solar_radiation_wm2": float|None, "comm_status": str}
    """
    result = {"solar_radiation_wm2": None, "comm_status": None}

    port = port or PORT
    if not port:
        result["comm_status"] = "PORT_NOT_SET"
        return result

    client = ModbusSerialClient(
        port=port,
        baudrate=BAUDRATE,
        bytesize=BYTESIZE,
        parity=PARITY,
        stopbits=STOPBITS,
        timeout=TIMEOUT,
        retries=RETRIES,
    )

    try:
        if not client.connect():
            result["comm_status"] = f"PORT_ERROR: {port} 열기 실패"
            return result

        raw, status = _read_register(client, slave_id)
        if raw is None:
            result["comm_status"] = status
            return result

        value = raw * SCALE
        if not (VALID_MIN <= value <= VALID_MAX):
            result["comm_status"] = f"OUT_OF_RANGE: {value}"
            return result

        result["solar_radiation_wm2"] = round(value, 1)
        result["comm_status"] = status
        return result

    except ModbusException as e:
        result["comm_status"] = f"MODBUS_ERROR: {e}"
        return result
    except Exception as e:
        result["comm_status"] = f"ERROR: {e}"
        return result
    finally:
        client.close()


def _read_register(client, slave_id):
    """FC03 우선, 실패하면 FC04로 재시도. (raw_value, status) 반환."""
    errors = []

    for func_name, reader in (
        ("FC03", client.read_holding_registers),
        ("FC04", client.read_input_registers),
    ):
        try:
            rr = reader(REG_ADDRESS, count=REG_COUNT, device_id=slave_id)
        except ModbusException as e:
            errors.append(f"{func_name}:{e}")
            continue

        if rr.isError():
            errors.append(f"{func_name}:{rr}")
            continue

        registers = getattr(rr, "registers", None)
        if not registers:
            errors.append(f"{func_name}:빈 응답")
            continue

        return registers[0], f"OK({func_name})"

    return None, "NO_RESPONSE: " + " / ".join(errors)


if __name__ == "__main__":
    # 연결 후 단독 확인용. PORT를 채우거나 인자로 넘겨서 실행한다.
    import sys

    cli_port = sys.argv[1] if len(sys.argv) > 1 else None
    print(read_solar_once(cli_port))
