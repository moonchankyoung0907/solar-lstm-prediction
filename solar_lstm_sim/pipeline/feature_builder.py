"""입력 텐서 구성 — (batch, SEQ_LEN, 8) 시퀀스 빌더"""

import logging

import numpy as np
import pandas as pd

from solar_lstm_sim.config import SEQ_LEN, PAST_STEPS, FUTURE_STEPS, NUM_FEATURES

logger = logging.getLogger(__name__)


def _time_features(timestamps: list) -> np.ndarray:
    """시간 인코딩: hour_sin, hour_cos, month_norm"""
    features = []
    for ts in timestamps:
        if isinstance(ts, str):
            ts = pd.Timestamp(ts)
        hour = ts.hour + ts.minute / 60.0
        hour_sin = np.sin(2 * np.pi * hour / 24.0)
        hour_cos = np.cos(2 * np.pi * hour / 24.0)
        month_norm = ts.month / 12.0
        features.append([hour_sin, hour_cos, month_norm])
    return np.array(features, dtype=np.float32)


def build_single_input(past_sensor: pd.DataFrame,
                       current_sensor: dict,
                       forecast_list: list[dict]) -> np.ndarray:
    """단일 예측용 입력 텐서 구성 → shape (1, SEQ_LEN, NUM_FEATURES)

    8 features:
      0: irradiance (actual)
      1: temp (module or air)
      2: power_actual
      3: irradiance_forecast
      4: temp_forecast
      5: hour_sin
      6: hour_cos
      7: month_norm
    """
    tensor = np.zeros((SEQ_LEN, NUM_FEATURES), dtype=np.float32)

    # ── 과거 24시간 실측 (t-24 ~ t-1) ──────────────
    past_len = min(len(past_sensor), PAST_STEPS)
    if past_len > 0:
        past_df = past_sensor.tail(past_len)
        start_idx = PAST_STEPS - past_len

        tensor[start_idx:PAST_STEPS, 0] = past_df["irradiance"].values[-past_len:]
        tensor[start_idx:PAST_STEPS, 1] = past_df["temp_module"].values[-past_len:]
        tensor[start_idx:PAST_STEPS, 2] = past_df["power_actual"].values[-past_len:]

        # 과거 시간 특성
        timestamps = list(past_df["timestamp"].values[-past_len:])
        tf = _time_features([pd.Timestamp(t) for t in timestamps])
        tensor[start_idx:PAST_STEPS, 5:8] = tf

    # ── 현재 실측 (t=0) ────────────────────────────
    idx_now = PAST_STEPS  # index 24
    tensor[idx_now, 0] = current_sensor.get("irradiance", 0)
    tensor[idx_now, 1] = current_sensor.get("temp_module", 0)
    tensor[idx_now, 2] = current_sensor.get("power_actual", 0)

    ts_now = current_sensor.get("timestamp", pd.Timestamp.now())
    tf_now = _time_features([pd.Timestamp(ts_now)])
    tensor[idx_now, 5:8] = tf_now[0]

    # ── 미래 10시간 예측 (t+1 ~ t+10) ──────────────
    for i, fc in enumerate(forecast_list[:FUTURE_STEPS]):
        idx = PAST_STEPS + 1 + i  # 25 ~ 34
        tensor[idx, 3] = fc.get("irradiance_forecast", 0)
        tensor[idx, 4] = fc.get("temp_forecast", 0)

        ft_time = fc.get("forecast_time", pd.Timestamp.now())
        tf_fc = _time_features([pd.Timestamp(ft_time)])
        tensor[idx, 5:8] = tf_fc[0]

    return tensor[np.newaxis, :, :]  # (1, SEQ_LEN, 8)


def build_sliding_windows(sensor_df: pd.DataFrame,
                          forecast_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """학습용 슬라이딩 윈도우 (X, y) 생성

    sensor_df: 전체 센서 데이터 (시간순)
    forecast_df: 전체 예측 데이터 (시간순)

    Returns:
        X: (N, SEQ_LEN, NUM_FEATURES)
        y: (N, FUTURE_STEPS) — 미래 10시간 실측 발전량
    """
    sensor_df = sensor_df.reset_index(drop=True)

    # 예측 데이터를 created_at 기준으로 그룹
    forecast_groups = {}
    for _, row in forecast_df.iterrows():
        key = row["created_at"]
        if key not in forecast_groups:
            forecast_groups[key] = []
        forecast_groups[key].append(row.to_dict())

    X_list = []
    y_list = []

    # 최소 PAST_STEPS + 1 + FUTURE_STEPS 이 있어야 윈도우 구성 가능
    min_idx = PAST_STEPS
    max_idx = len(sensor_df) - FUTURE_STEPS

    for i in range(min_idx, max_idx):
        current_row = sensor_df.iloc[i]
        current_ts = current_row["timestamp"]

        # 과거 24시간
        past = sensor_df.iloc[max(0, i - PAST_STEPS):i]
        if len(past) < PAST_STEPS:
            continue

        # 미래 10시간 실측 (타겟)
        future = sensor_df.iloc[i + 1:i + 1 + FUTURE_STEPS]
        if len(future) < FUTURE_STEPS:
            continue
        y_vals = future["power_actual"].values.astype(np.float32)

        # 해당 시점의 예측 데이터 찾기
        fc_data = forecast_groups.get(current_ts, [])
        if len(fc_data) < FUTURE_STEPS:
            # 예측 데이터가 없으면 0으로 패딩된 상태 유지
            fc_data = [{"irradiance_forecast": 0, "temp_forecast": 0,
                        "forecast_time": current_ts} for _ in range(FUTURE_STEPS)]

        current_dict = current_row.to_dict()
        x = build_single_input(past, current_dict, fc_data)  # (1, SEQ_LEN, 8)
        X_list.append(x[0])
        y_list.append(y_vals)

    if not X_list:
        return np.empty((0, SEQ_LEN, NUM_FEATURES)), np.empty((0, FUTURE_STEPS))

    X = np.stack(X_list, axis=0)  # (N, SEQ_LEN, 8)
    y = np.stack(y_list, axis=0)  # (N, 10)
    logger.info("Built %d sliding windows.", len(X))
    return X, y
