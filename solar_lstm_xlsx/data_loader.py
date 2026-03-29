"""train_log.xlsx 데이터 로더"""

import logging

import pandas as pd
import numpy as np

from solar_lstm_xlsx.config import DATA_PATH, NOCT

logger = logging.getLogger(__name__)


def load_xlsx(path=None) -> pd.DataFrame:
    """train_log.xlsx → 통합 DataFrame

    반환 컬럼:
        timestamp, irradiance, temp_module, temp_air,
        power_actual, irr_forecast, temp_forecast
    """
    path = path or DATA_PATH
    raw = pd.read_excel(path, sheet_name=0, engine="openpyxl")
    logger.info("Loaded %d rows from %s", len(raw), path)

    # 타임스탬프 생성
    raw["hour"] = raw["시간"].str.replace("시", "").astype(int)
    raw["timestamp"] = pd.to_datetime(raw["날짜"]) + pd.to_timedelta(raw["hour"], unit="h")

    # 컬럼 매핑
    df = pd.DataFrame()
    df["timestamp"] = raw["timestamp"]
    df["irradiance"] = pd.to_numeric(raw["일사량(W/㎡)"], errors="coerce").fillna(0).clip(lower=0)
    df["temp_air"] = pd.to_numeric(raw["기온(℃)"], errors="coerce").fillna(0)
    df["power_actual"] = pd.to_numeric(raw["발전량(kW)"], errors="coerce").fillna(0).clip(lower=0)
    df["irr_forecast"] = pd.to_numeric(raw["예측 일사량(W/㎡)"], errors="coerce").fillna(0).clip(lower=0)
    df["temp_forecast"] = pd.to_numeric(raw["예측 기온(℃)"], errors="coerce").fillna(0)

    # 모듈 온도 계산 (NOCT 공식)
    df["temp_module"] = df["temp_air"] + (NOCT - 20) / 800.0 * df["irradiance"]

    # 시간순 정렬
    df = df.sort_values("timestamp").reset_index(drop=True)

    logger.info("Data range: %s ~ %s (%d hours)",
                df["timestamp"].iloc[0], df["timestamp"].iloc[-1], len(df))
    return df
