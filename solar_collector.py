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

스케줄러 등록(포트 확정 후 1회만):
  schtasks /Create /TN SolarCollector /SC MINUTE /MO 5 ^
    /TR "C:\Users\sejae\AppData\Local\Programs\Python\Python311\python.exe C:\Users\sejae\Desktop\solar_collector.py"
"""

import os
from datetime import datetime

import openpyxl

from solar_reader import read_solar_once

XLSX_PATH = r"C:\Users\sejae\Desktop\solar_log.xlsx"
HEADER = ["datetime", "solar_radiation_wm2", "comm_status"]


def main():
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
    print(f"{row[0]} - {row[1]} W/m² - {row[2]}")


if __name__ == "__main__":
    main()
