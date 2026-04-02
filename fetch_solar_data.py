"""
fetch_solar_data.py
===================
사천 태양광 발전소 — 일별 데이터 수집 및 log.xlsx 누적 저장

실행 방법
---------
  # 즉시 실행 (어제 날짜 기준)
  python fetch_solar_data.py --run-now

  # 스케줄러 모드 (매일 자정 자동 실행)
  python fetch_solar_data.py

데이터 소스
-----------
  실측 날씨  : Open-Meteo Archive API (archive-api.open-meteo.com)
  예측 날씨  : Open-Meteo Forecast API (api.open-meteo.com)
  실측 발전량: 인버터 CSV 파일 (INVERTER_DIR/*.csv) 또는 물리 모델 추정
  예측 발전량: 예측 일사량 기반 물리 모델 계산

저장 형식
---------
  log.xlsx      : 실측·예측 비교 (12컬럼, 시간별 누적)
  train_log.xlsx: LSTM 학습용 포맷 (7컬럼, 시간별 누적)
"""

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from apscheduler.schedulers.blocking import BlockingScheduler

# ── 로거 설정 ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("fetch_solar_data.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("fetch_solar")

# ═══════════════════════════════════════════════════════════════════════════════
# 설정 (발전소별 값으로 수정하세요)
# ═══════════════════════════════════════════════════════════════════════════════

# 발전소 위치 — 경남 사천시
LAT = 34.9418
LON = 128.0635

# 태양광 시스템 사양
CAPACITY_KW   = 100.0   # 설비 용량 (kW)
EFFICIENCY    = 0.96    # 인버터 효율
PERF_RATIO    = 0.85    # 성능 비율 (PR)
NOCT          = 45      # 공칭 동작 셀 온도 (℃)
PEAK_IRR      = 1000.0  # 기준 일사량 (W/m²)

# 파일 경로
BASE_DIR      = Path(__file__).resolve().parent
LOG_PATH      = BASE_DIR / "log.xlsx"
TRAIN_LOG_PATH = BASE_DIR / "train_log.xlsx"

# 인버터 CSV 디렉터리 (파일명 형식: YYYYMMDD.csv 또는 inverter_YYYYMMDD.csv)
# CSV 컬럼: hour(0~23), power_kw
# 파일이 없으면 물리 모델로 발전량 추정
INVERTER_DIR  = BASE_DIR / "inverter_data"

# Open-Meteo API
ARCHIVE_URL  = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# log.xlsx 컬럼명 (기존 파일과 동일하게 유지)
LOG_COLUMNS = [
    "날짜",
    "시간",
    "실제 발전량(kW)",
    "실제 누적발전량(kWh)",
    "실제 일사량(W/㎡)",
    "실제 기온(℃)",
    "실제 풍속(㎧)",
    "예측 발전량(kW)",
    "예측 누적발전량(kWh)",
    "예측 일사량(W/㎡)",
    "예측 기온(℃)",
    "예측 풍속(㎧)",
]

# train_log.xlsx 컬럼명
TRAIN_COLUMNS = [
    "날짜",
    "시간",
    "발전량(kW)",
    "일사량(W/㎡)",
    "기온(℃)",
    "예측 일사량(W/㎡)",
    "예측 기온(℃)",
]

# ═══════════════════════════════════════════════════════════════════════════════
# 날씨 API 호출
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_actual_weather(target_date: date) -> dict[int, dict]:
    """Open-Meteo 아카이브 API → 실측 기상 데이터 (시간별)

    Returns:
        {hour: {irradiance, temperature, windspeed}}
    """
    date_str = target_date.strftime("%Y-%m-%d")
    params = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": date_str,
        "end_date": date_str,
        "hourly": "shortwave_radiation,temperature_2m,windspeed_10m",
        "timezone": "Asia/Seoul",
    }
    try:
        resp = requests.get(ARCHIVE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()["hourly"]

        result = {}
        for i, ts in enumerate(data["time"]):
            hour = int(ts[11:13])
            result[hour] = {
                "irradiance": max(0.0, float(data["shortwave_radiation"][i] or 0)),
                "temperature": float(data["temperature_2m"][i] or 0),
                "windspeed":   float(data["windspeed_10m"][i] or 0),
            }
        logger.info("Actual weather fetched for %s (%d hours)", date_str, len(result))
        return result
    except Exception as e:
        logger.error("Failed to fetch actual weather: %s", e)
        return {}


def fetch_forecast_weather(target_date: date) -> dict[int, dict]:
    """Open-Meteo 예보 API → 특정 날짜의 시간별 예보

    - 미래/당일: Forecast API 사용
    - 과거 날짜: Archive API로 폴백 (실측값을 예보값으로 대체)

    Returns:
        {hour: {irradiance, temperature, windspeed}}
    """
    date_str = target_date.strftime("%Y-%m-%d")
    today = date.today()

    # 미래/당일은 Forecast API
    if target_date >= today - timedelta(days=1):
        params = {
            "latitude": LAT,
            "longitude": LON,
            "start_date": date_str,
            "end_date": date_str,
            "hourly": "shortwave_radiation,temperature_2m,windspeed_10m",
            "timezone": "Asia/Seoul",
            "forecast_days": 3,
        }
        try:
            resp = requests.get(FORECAST_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()["hourly"]
            result = {}
            for i, ts in enumerate(data["time"]):
                if ts[:10] != date_str:
                    continue
                hour = int(ts[11:13])
                result[hour] = {
                    "irradiance": max(0.0, float(data["shortwave_radiation"][i] or 0)),
                    "temperature": float(data["temperature_2m"][i] or 0),
                    "windspeed":   float(data["windspeed_10m"][i] or 0),
                }
            logger.info("Forecast weather fetched (API) for %s (%d hours)", date_str, len(result))
            return result
        except Exception as e:
            logger.warning("Forecast API failed (%s), falling back to archive.", e)

    # 과거 날짜 또는 Forecast API 실패 → Archive로 폴백
    logger.info("Using archive API as forecast fallback for %s", date_str)
    return fetch_actual_weather(target_date)

# ═══════════════════════════════════════════════════════════════════════════════
# 인버터 발전량 로딩
# ═══════════════════════════════════════════════════════════════════════════════

def load_inverter_power(target_date: date) -> dict[int, float] | None:
    """인버터 CSV에서 시간별 발전량(kW) 로드

    CSV 형식 예시 (헤더 필수):
        hour,power_kw
        0,0.0
        1,0.0
        ...
        12,87.3
        ...

    파일명 패턴: YYYYMMDD.csv 또는 inverter_YYYYMMDD.csv
    """
    if not INVERTER_DIR.exists():
        return None

    date_str = target_date.strftime("%Y%m%d")
    candidates = [
        INVERTER_DIR / f"{date_str}.csv",
        INVERTER_DIR / f"inverter_{date_str}.csv",
    ]
    for path in candidates:
        if path.exists():
            try:
                df = pd.read_csv(path)
                if "hour" in df.columns and "power_kw" in df.columns:
                    result = {int(row["hour"]): float(row["power_kw"]) for _, row in df.iterrows()}
                    logger.info("Inverter data loaded from %s", path.name)
                    return result
            except Exception as e:
                logger.warning("Could not read %s: %s", path, e)
    return None


def estimate_power(irradiance: float, temp_air: float) -> float:
    """물리 모델 기반 발전량 추정 (인버터 데이터 없을 때)

    P = Capacity × (Irr / 1000) × efficiency × PR × temp_derating
    """
    if irradiance <= 0:
        return 0.0
    temp_module = temp_air + (NOCT - 20.0) / 800.0 * irradiance
    temp_derating = 1.0 - 0.004 * max(0.0, temp_module - 25.0)
    power = CAPACITY_KW * (irradiance / PEAK_IRR) * EFFICIENCY * PERF_RATIO * temp_derating
    return max(0.0, round(power, 2))

# ═══════════════════════════════════════════════════════════════════════════════
# 데이터 조합 및 저장
# ═══════════════════════════════════════════════════════════════════════════════

def build_log_rows(target_date: date) -> pd.DataFrame:
    """target_date의 24시간 데이터 행 생성"""
    date_str = target_date.strftime("%Y-%m-%d")
    logger.info("Building rows for %s", date_str)

    actual_weather  = fetch_actual_weather(target_date)
    forecast_weather = fetch_forecast_weather(target_date)
    inverter_power   = load_inverter_power(target_date)

    rows = []
    actual_cum  = 0.0
    forecast_cum = 0.0

    for hour in range(24):
        aw = actual_weather.get(hour,   {"irradiance": 0.0, "temperature": 0.0, "windspeed": 0.0})
        fw = forecast_weather.get(hour, {"irradiance": 0.0, "temperature": 0.0, "windspeed": 0.0})

        # 실제 발전량
        if inverter_power and hour in inverter_power:
            act_power = max(0.0, inverter_power[hour])
        else:
            act_power = estimate_power(aw["irradiance"], aw["temperature"])
        actual_cum += act_power

        # 예측 발전량
        fct_power = estimate_power(fw["irradiance"], fw["temperature"])
        forecast_cum += fct_power

        rows.append({
            "날짜": date_str,
            "시간": f"{hour}시",
            "실제 발전량(kW)":    round(act_power, 2),
            "실제 누적발전량(kWh)": round(actual_cum, 2),
            "실제 일사량(W/㎡)":   round(aw["irradiance"], 1),
            "실제 기온(℃)":        round(aw["temperature"], 1),
            "실제 풍속(㎧)":        round(aw["windspeed"], 1),
            "예측 발전량(kW)":    round(fct_power, 2),
            "예측 누적발전량(kWh)": round(forecast_cum, 2),
            "예측 일사량(W/㎡)":   round(fw["irradiance"], 1),
            "예측 기온(℃)":        round(fw["temperature"], 1),
            "예측 풍속(㎧)":        round(fw["windspeed"], 1),
        })

    return pd.DataFrame(rows, columns=LOG_COLUMNS)


def build_train_rows(log_df: pd.DataFrame, target_date: date) -> pd.DataFrame:
    """log_df → train_log.xlsx 형식 변환 (7컬럼)"""
    rows = []
    date_str = target_date.strftime("%Y-%m-%d")
    for _, row in log_df.iterrows():
        rows.append({
            "날짜":              date_str,
            "시간":              row["시간"],
            "발전량(kW)":        row["실제 발전량(kW)"],
            "일사량(W/㎡)":       row["실제 일사량(W/㎡)"],
            "기온(℃)":           row["실제 기온(℃)"],
            "예측 일사량(W/㎡)":  row["예측 일사량(W/㎡)"],
            "예측 기온(℃)":      row["예측 기온(℃)"],
        })
    return pd.DataFrame(rows, columns=TRAIN_COLUMNS)


def append_to_excel(new_df: pd.DataFrame, path: Path, columns: list[str]):
    """기존 xlsx에 새 행을 중복 없이 누적 저장"""
    date_val = new_df["날짜"].iloc[0]

    if path.exists():
        existing = pd.read_excel(path, engine="openpyxl")
        # 기존 컬럼이 깨진 경우 덮어쓰기
        if list(existing.columns) != columns:
            existing.columns = columns
        # 같은 날짜 중복 제거
        existing = existing[existing["날짜"].astype(str) != str(date_val)]
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_excel(path, index=False, engine="openpyxl")
    logger.info("Saved %d rows to %s (date=%s)", len(new_df), path.name, date_val)

# ═══════════════════════════════════════════════════════════════════════════════
# 일별 수집 메인 작업
# ═══════════════════════════════════════════════════════════════════════════════

def daily_job(target_date: date | None = None):
    """매일 자정에 실행: 어제 하루치 데이터 수집 및 저장"""
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    logger.info("=== Daily fetch start: %s ===", target_date)

    try:
        log_df   = build_log_rows(target_date)
        train_df = build_train_rows(log_df, target_date)

        append_to_excel(log_df,   LOG_PATH,       LOG_COLUMNS)
        append_to_excel(train_df, TRAIN_LOG_PATH, TRAIN_COLUMNS)

        # 요약 출력
        total_act = log_df["실제 발전량(kW)"].sum()
        total_fct = log_df["예측 발전량(kW)"].sum()
        logger.info(
            "Summary | actual=%.1f kWh  forecast=%.1f kWh  date=%s",
            total_act, total_fct, target_date,
        )
    except Exception as e:
        logger.exception("daily_job failed: %s", e)

    logger.info("=== Daily fetch done ===")

# ═══════════════════════════════════════════════════════════════════════════════
# 진입점
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="사천 태양광 데이터 수집기")
    parser.add_argument(
        "--run-now", action="store_true",
        help="즉시 실행 (어제 데이터 수집). 기본값: 스케줄러 모드",
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="특정 날짜 수집 (YYYY-MM-DD). --run-now와 함께 사용",
    )
    args = parser.parse_args()

    if args.run_now:
        target = date.fromisoformat(args.date) if args.date else None
        daily_job(target)
        return

    # ── 스케줄러 모드: 매일 자정 실행 ──
    logger.info("Scheduler mode: will run daily at 00:00 Asia/Seoul")
    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        daily_job,
        trigger="cron",
        hour=0,
        minute=0,
        id="daily_solar_fetch",
        name="사천 태양광 일별 데이터 수집",
        misfire_grace_time=300,   # 5분 이내 지연 허용
        coalesce=True,
    )

    logger.info("Next run: %s", scheduler.get_jobs()[0].next_run_time)

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user.")


if __name__ == "__main__":
    main()
