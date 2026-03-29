"""전처리 — IQR 이상치 제거, 선형 보간, 야간 마스킹"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

NUMERIC_COLS = ["irradiance", "temp_module", "temp_air", "power_actual",
                "irr_forecast", "temp_forecast"]


def remove_outliers_iqr(df: pd.DataFrame, columns: list[str], factor: float = 1.5) -> pd.DataFrame:
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            continue
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        lower, upper = q1 - factor * iqr, q3 + factor * iqr
        mask = (df[col] < lower) | (df[col] > upper)
        if mask.sum() > 0:
            logger.debug("Column '%s': %d outliers replaced.", col, mask.sum())
            df.loc[mask, col] = np.nan
    return df


def interpolate_missing(df: pd.DataFrame) -> pd.DataFrame:
    return df.interpolate(method="linear", limit_direction="both").ffill().bfill()


def mask_nighttime(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    hour = df["timestamp"].dt.hour
    night = (hour >= 21) | (hour < 6)
    for col in ["irradiance", "power_actual"]:
        if col in df.columns:
            df.loc[night, col] = 0.0
    return df


def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    df = remove_outliers_iqr(df, NUMERIC_COLS)
    df = interpolate_missing(df)
    df = mask_nighttime(df)
    return df
