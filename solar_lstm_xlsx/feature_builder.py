"""입력 텐서 구성 — (batch, 35, 8) 시퀀스 빌더"""

import logging

import numpy as np
import pandas as pd

from solar_lstm_xlsx.config import SEQ_LEN, PAST_STEPS, FUTURE_STEPS, NUM_FEATURES

logger = logging.getLogger(__name__)


def _time_features(timestamps) -> np.ndarray:
    """hour_sin, hour_cos, month_norm"""
    result = []
    for ts in timestamps:
        ts = pd.Timestamp(ts)
        hour = ts.hour + ts.minute / 60.0
        result.append([
            np.sin(2 * np.pi * hour / 24.0),
            np.cos(2 * np.pi * hour / 24.0),
            ts.month / 12.0,
        ])
    return np.array(result, dtype=np.float32)


def build_sliding_windows(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """학습용 슬라이딩 윈도우 생성

    8 features: irr, temp_module, power, irr_fore, temp_fore, hour_sin, hour_cos, month_norm

    Returns:
        X: (N, 35, 8)
        y: (N, 10) — 미래 10시간 실측 발전량
    """
    df = df.reset_index(drop=True)
    timestamps = df["timestamp"].values

    X_list, y_list = [], []

    for i in range(PAST_STEPS, len(df) - FUTURE_STEPS):
        # 과거 24시간 충분한지 확인
        past = df.iloc[i - PAST_STEPS:i]
        if len(past) < PAST_STEPS:
            continue

        # 미래 10시간 타겟
        future = df.iloc[i + 1:i + 1 + FUTURE_STEPS]
        if len(future) < FUTURE_STEPS:
            continue

        tensor = np.zeros((SEQ_LEN, NUM_FEATURES), dtype=np.float32)

        # ── 과거 24시간 (index 0~23) ──
        tensor[:PAST_STEPS, 0] = past["irradiance"].values
        tensor[:PAST_STEPS, 1] = past["temp_module"].values
        tensor[:PAST_STEPS, 2] = past["power_actual"].values
        tf_past = _time_features(past["timestamp"].values)
        tensor[:PAST_STEPS, 5:8] = tf_past

        # ── 현재 (index 24) ──
        current = df.iloc[i]
        tensor[PAST_STEPS, 0] = current["irradiance"]
        tensor[PAST_STEPS, 1] = current["temp_module"]
        tensor[PAST_STEPS, 2] = current["power_actual"]
        tf_now = _time_features([current["timestamp"]])
        tensor[PAST_STEPS, 5:8] = tf_now[0]

        # ── 미래 10시간 예측 (index 25~34) ──
        tensor[PAST_STEPS + 1:, 3] = future["irr_forecast"].values
        tensor[PAST_STEPS + 1:, 4] = future["temp_forecast"].values
        tf_future = _time_features(future["timestamp"].values)
        tensor[PAST_STEPS + 1:, 5:8] = tf_future

        # ── 타겟: 미래 10시간 실측 발전량 ──
        y_vals = future["power_actual"].values.astype(np.float32)

        X_list.append(tensor)
        y_list.append(y_vals)

    X = np.stack(X_list, axis=0)
    y = np.stack(y_list, axis=0)
    logger.info("Built %d sliding windows.", len(X))
    return X, y


def build_single_input(df: pd.DataFrame, current_idx: int) -> np.ndarray:
    """단일 예측용 입력 텐서 → (1, 35, 8)"""
    tensor = np.zeros((SEQ_LEN, NUM_FEATURES), dtype=np.float32)

    # 과거 24시간
    start = max(0, current_idx - PAST_STEPS)
    past = df.iloc[start:current_idx]
    n = len(past)
    offset = PAST_STEPS - n
    tensor[offset:PAST_STEPS, 0] = past["irradiance"].values
    tensor[offset:PAST_STEPS, 1] = past["temp_module"].values
    tensor[offset:PAST_STEPS, 2] = past["power_actual"].values
    tf_past = _time_features(past["timestamp"].values)
    tensor[offset:PAST_STEPS, 5:8] = tf_past

    # 현재
    current = df.iloc[current_idx]
    tensor[PAST_STEPS, 0] = current["irradiance"]
    tensor[PAST_STEPS, 1] = current["temp_module"]
    tensor[PAST_STEPS, 2] = current["power_actual"]
    tf_now = _time_features([current["timestamp"]])
    tensor[PAST_STEPS, 5:8] = tf_now[0]

    # 미래 10시간 예측
    future_end = min(current_idx + 1 + FUTURE_STEPS, len(df))
    future = df.iloc[current_idx + 1:future_end]
    n_f = len(future)
    if n_f > 0:
        tensor[PAST_STEPS + 1:PAST_STEPS + 1 + n_f, 3] = future["irr_forecast"].values
        tensor[PAST_STEPS + 1:PAST_STEPS + 1 + n_f, 4] = future["temp_forecast"].values
        tf_future = _time_features(future["timestamp"].values)
        tensor[PAST_STEPS + 1:PAST_STEPS + 1 + n_f, 5:8] = tf_future

    return tensor[np.newaxis, :, :]
