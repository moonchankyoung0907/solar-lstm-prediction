"""전처리 — IQR 이상치 제거, 선형 보간, 야간 마스킹, 품질 검증"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_SENSOR_COLS = ["irradiance", "temp_module", "temp_air", "power_actual"]
REQUIRED_FORECAST_COLS = ["irradiance_forecast", "temp_forecast"]


def remove_outliers_iqr(df: pd.DataFrame, columns: list[str], factor: float = 1.5) -> pd.DataFrame:
    """IQR 기반 이상치를 NaN 으로 교체"""
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            continue
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        lower = q1 - factor * iqr
        upper = q3 + factor * iqr
        outlier_mask = (df[col] < lower) | (df[col] > upper)
        n_outliers = outlier_mask.sum()
        if n_outliers > 0:
            logger.debug("Column '%s': %d outliers replaced with NaN.", col, n_outliers)
            df.loc[outlier_mask, col] = np.nan
    return df


def interpolate_missing(df: pd.DataFrame) -> pd.DataFrame:
    """선형 보간으로 NaN 채움"""
    return df.interpolate(method="linear", limit_direction="both").ffill().bfill()


def mask_nighttime(df: pd.DataFrame, hour_col: str = "hour") -> pd.DataFrame:
    """야간(21:00~05:00) 일사량·발전량을 0으로"""
    df = df.copy()
    if hour_col not in df.columns and "timestamp" in df.columns:
        df[hour_col] = pd.to_datetime(df["timestamp"]).dt.hour
    if hour_col in df.columns:
        night = (df[hour_col] >= 21) | (df[hour_col] < 6)
        for col in ["irradiance", "power_actual"]:
            if col in df.columns:
                df.loc[night, col] = 0.0
    return df


def validate_quality(df: pd.DataFrame, required_cols: list[str]) -> bool:
    """데이터 품질 검증: 필수 컬럼 존재 + 값 범위 정상"""
    for col in required_cols:
        if col not in df.columns:
            logger.error("Missing required column: %s", col)
            return False

    if "irradiance" in df.columns and (df["irradiance"].max() > 1500 or df["irradiance"].min() < -1):
        logger.error("Irradiance out of range [0, 1500].")
        return False

    if "power_actual" in df.columns and df["power_actual"].min() < -1:
        logger.error("Power actual has negative values.")
        return False

    if df.isnull().sum().sum() > len(df) * len(df.columns) * 0.3:
        logger.error("Too many NaN values (>30%%).")
        return False

    return True


def preprocess_sensor(df: pd.DataFrame) -> pd.DataFrame:
    """센서 데이터 전처리 파이프라인"""
    df = remove_outliers_iqr(df, REQUIRED_SENSOR_COLS)
    df = interpolate_missing(df)
    df = mask_nighttime(df)
    return df
