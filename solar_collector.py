r"""
일사량 센서(vctec P000BDFU / PYR20) - 5분 주기 폴링 -> solar_log.xlsx 누적

inverter_collector.py와 같은 구조다. Windows 작업 스케줄러가 5분 간격으로 실행한다.
sensor_log.xlsx를 직접 건드리지 않고 별도 파일에 쌓는 이유:
  - sensor_log.xlsx는 collector.py가 30분마다(auto_push.bat 안에서) 통째로 열고 저장한다.
    같은 파일을 5분 주기 작업이 동시에 열면 파일 잠금이 충돌한다.
  - sensor_log.xlsx의 행은 WH24Data.txt의 16초 간격 타임스탬프로 만들어지므로,
    5분 주기로 읽은 일사량을 실시간으로 그 행에 직접 써 넣을 수 없다.
  → 여기서는 원본만 쌓고, collector.py가 실행될 때 타임스탬프를 맞춰
    sensor_log.xlsx의 solar_radiation_wm2 컬럼으로 합친다.

콘솔에는 아무것도 쓰지 않는다. 작업 스케줄러가 띄운 콘솔 창이 빠른 편집(선택) 상태가 되면
print()가 막혀 프로세스가 끝나지 않는다(2026-10-08 InverterCollector 72시간 정지 추정 원인).
결과/예외는 tmp\solar_collector.log에 한 줄씩 남긴다(1MB 넘으면 .1로 회전).

스케줄러 등록(포트 확정 후 1회만):
  schtasks /Create /TN SolarCollector /SC MINUTE /MO 5 ^
    /TR "C:\Users\sejae\AppData\Local\Programs\Python\Python311\python.exe C:\Users\sejae\Desktop\solar_collector.py"
"""

import os
import sys
import time
import traceback
from datetime import datetime

XLSX_PATH = r"C:\Users\sejae\Desktop\solar_log.xlsx"
LOG_PATH = r"C:\Users\sejae\Desktop\tmp\solar_collector.log"
LOG_MAX_BYTES = 1024 * 1024
HEADER = ["datetime", "solar_radiation_wm2", "comm_status"]


def _log(msg):
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > LOG_MAX_BYTES:
            os.replace(LOG_PATH, LOG_PATH + ".1")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} pid={os.getpid()} {msg}\n")
    except OSError:
        pass


def main():
    import openpyxl

    from solar_reader import read_solar_once

    if os.path.exists(XLSX_PATH):
        wb = openpyxl.load_workbook(XLSX_PATH)
        ws = wb.active
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "solar"
        ws.append(HEADER)

    data = read_solar_once()
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        data["solar_radiation_wm2"],
        data["comm_status"],
    ]
    ws.append(row)

    wb.save(XLSX_PATH)
    return f"{row[2]} {row[1]}W/m2"


if __name__ == "__main__":
    # 라이브러리 경고 등 어떤 출력도 콘솔로 가지 않게 막는다.
    sys.stdout = sys.stderr = open(os.devnull, "w")
    t0 = time.monotonic()
    try:
        status = main()
    except BaseException as e:
        _log(f"ERROR {time.monotonic() - t0:.1f}s {type(e).__name__}: {e}")
        _log("TRACEBACK " + traceback.format_exc().replace("\n", " | "))
        os._exit(1)
    _log(f"{status} {time.monotonic() - t0:.1f}s")
