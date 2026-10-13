"""
DASS DSP-123K7C-OD 인버터 - 5분 주기 폴링 -> inverter_log.xlsx 누적

Windows 작업 스케줄러에서 5분 간격으로 이 스크립트를 실행한다.
sensor_log.xlsx(날씨, WH24Collector 작업이 매일 다룸)와는 완전히 별도 파일이라
서로 파일 잠금 충돌이 없다.

콘솔에는 아무것도 쓰지 않는다. 작업 스케줄러가 띄운 콘솔 창이 빠른 편집(선택) 상태가 되면
print()가 막혀 프로세스가 끝나지 않는다(2026-10-08 72시간 정지 추정 원인).
결과/예외는 tmp\\inverter_collector.log에 한 줄씩 남긴다(1MB 넘으면 .1로 회전).
"""

import os
import sys
import time
import traceback
from datetime import datetime

XLSX_PATH = r"C:\Users\sejae\Desktop\inverter_log.xlsx"
LOG_PATH = r"C:\Users\sejae\Desktop\tmp\inverter_collector.log"
LOG_MAX_BYTES = 1024 * 1024


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

    from inverter_reader import FIELDS as INVERTER_FIELDS
    from inverter_reader import read_inverter_once

    header = ["datetime"] + INVERTER_FIELDS + ["comm_status"]
    if os.path.exists(XLSX_PATH):
        wb = openpyxl.load_workbook(XLSX_PATH)
        ws = wb.active
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "inverter"
        ws.append(header)

    data = read_inverter_once()
    row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
    row += [data[f] for f in INVERTER_FIELDS]
    row += [data["comm_status"]]
    ws.append(row)

    wb.save(XLSX_PATH)
    return data["comm_status"]


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
