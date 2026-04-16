"""log.xlsx 저장 모듈

기존 log.xlsx 시트에 수집 행을 추가(append)합니다.
컬럼 구조 (기존 파일 기준):
  날짜 | 시간 | 실제 발전량(kW) | 실제 누적발전량(kWh) |
  실제 일사량(W/㎡) | 실제 기온(℃) | 실제 풍속(㎧) |
  예측 발전량(kW) | 예측 누적발전량(kWh) |
  예측 일사량(W/㎡) | 예측 기온(℃) | 예측 풍속(㎧)
"""

import logging
import pathlib
from datetime import datetime
from typing import Optional

import openpyxl

from collector.protocols.bms_reader import BmsData
from collector.protocols.meter_reader import MeterData
from collector.protocols.weather_reader import WeatherData

logger = logging.getLogger(__name__)

# log.xlsx 컬럼 순서 (0-based index)
_COL_DATE        = 0
_COL_TIME        = 1
_COL_POWER_KW    = 2   # 실제 발전량(kW)
_COL_ENERGY_KWH  = 3   # 실제 누적발전량(kWh)
_COL_IRR         = 4   # 실제 일사량(W/㎡)
_COL_TEMP        = 5   # 실제 기온(℃)
_COL_WIND        = 6   # 실제 풍속(㎧)
# 예측 컬럼(7~11)은 이 수집기가 채우지 않음 — LSTM 예측 모듈이 담당


def append_row(
    xlsx_path: pathlib.Path,
    ts: datetime,
    meter: MeterData,
    weather: WeatherData,
    bms: Optional[BmsData] = None,
) -> None:
    """수집 데이터 1행을 log.xlsx에 추가"""
    xlsx_path = pathlib.Path(xlsx_path)

    if xlsx_path.exists():
        wb = openpyxl.load_workbook(xlsx_path)
        ws = wb.active
    else:
        logger.warning("[Writer] %s 없음 — 새 파일 생성", xlsx_path)
        wb = openpyxl.Workbook()
        ws = wb.active
        _write_header(ws)

    row = _build_row(ts, meter, weather)
    ws.append(row)
    wb.save(xlsx_path)
    logger.info("[Writer] 저장 완료: %s %s  전력=%.2f kW  일사=%.1f W/m²  기온=%.1f℃",
                row[_COL_DATE], row[_COL_TIME],
                row[_COL_POWER_KW], row[_COL_IRR], row[_COL_TEMP])


def _build_row(ts: datetime, meter: MeterData, weather: WeatherData) -> list:
    """컬럼 순서에 맞는 1행 리스트 생성 (예측 컬럼은 None)"""
    row = [None] * 12
    row[_COL_DATE]       = ts.strftime("%Y-%m-%d")
    row[_COL_TIME]       = f"{ts.hour}시"
    row[_COL_POWER_KW]   = round(meter.power_kw, 2)    if meter.ok else None
    row[_COL_ENERGY_KWH] = round(meter.energy_kwh, 2)  if meter.ok else None
    row[_COL_IRR]        = round(weather.irradiance_wm2, 1) if weather.ok else None
    row[_COL_TEMP]       = round(weather.temperature_c, 1)  if weather.ok else None
    row[_COL_WIND]       = round(weather.wind_speed_ms, 1)  if weather.ok else None
    # 예측 컬럼 7~11: None (LSTM 모듈이 채움)
    return row


def _write_header(ws) -> None:
    ws.append([
        "날짜", "시간",
        "실제 발전량(kW)", "실제 누적발전량(kWh)",
        "실제 일사량(W/㎡)", "실제 기온(℃)", "실제 풍속(㎧)",
        "예측 발전량(kW)", "예측 누적발전량(kWh)",
        "예측 일사량(W/㎡)", "예측 기온(℃)", "예측 풍속(㎧)",
    ])
