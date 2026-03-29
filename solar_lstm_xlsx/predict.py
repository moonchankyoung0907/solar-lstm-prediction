"""예측 — 학습된 모델로 특정 시점의 10시간 발전량 예측"""

import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import numpy as np
import pandas as pd

from solar_lstm_xlsx.config import MODEL_PATH, SCALER_PATH, FUTURE_STEPS, CONFIDENCE_LOWER, CONFIDENCE_UPPER
from solar_lstm_xlsx.data_loader import load_xlsx
from solar_lstm_xlsx.preprocessor import preprocess
from solar_lstm_xlsx.feature_builder import build_single_input
from solar_lstm_xlsx.scaler import SolarScaler
from solar_lstm_xlsx.lstm_model import load_model, predict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main(xlsx_path=None, target_datetime=None):
    """특정 시점 기준 10시간 예측

    Args:
        xlsx_path: 데이터 파일 경로 (기본: train_log.xlsx)
        target_datetime: 예측 기준 시각 (기본: 데이터의 마지막에서 11시간 전)
    """
    # 1. 데이터 로드
    df = load_xlsx(xlsx_path)
    df = preprocess(df)

    # 2. 예측 기준 시점 결정
    if target_datetime:
        target_ts = pd.Timestamp(target_datetime)
        idx = df[df["timestamp"] == target_ts].index
        if len(idx) == 0:
            logger.error("Target datetime %s not found in data.", target_ts)
            return
        current_idx = idx[0]
    else:
        current_idx = len(df) - FUTURE_STEPS - 1

    current_ts = df.iloc[current_idx]["timestamp"]
    logger.info("Prediction base time: %s", current_ts)

    # 3. 모델/스케일러 로드
    if not MODEL_PATH.exists() or not SCALER_PATH.exists():
        logger.error("Model or scaler not found. Run train.py first.")
        return

    model = load_model()
    scaler = SolarScaler()
    scaler.load()

    # 4. 입력 텐서 구성
    X = build_single_input(df, current_idx)
    X_scaled = scaler.transform_x(X)

    # 5. 예측 + 역정규화
    y_pred_scaled = predict(model, X_scaled)
    y_pred = scaler.inverse_y(y_pred_scaled)
    y_pred = np.clip(y_pred, 0, None)
    predictions = y_pred[0]

    # 6. 신뢰구간
    lower = predictions * CONFIDENCE_LOWER
    upper = predictions * CONFIDENCE_UPPER

    # 7. 실측값 비교 (있으면)
    print()
    print("=" * 78)
    print(f"  10-Hour Solar Power Forecast from {current_ts}")
    print("=" * 78)
    print(f"  {'hour':>6} | {'target_time':>18} | {'predicted(kW)':>14} | {'lower':>10} | {'upper':>10} | {'actual':>10}")
    print(f"  {'-'*72}")

    for h in range(FUTURE_STEPS):
        target_idx = current_idx + 1 + h
        target_ts = current_ts + pd.Timedelta(hours=h + 1)

        actual_str = ""
        if target_idx < len(df):
            actual = df.iloc[target_idx]["power_actual"]
            actual_str = f"{actual:>10.2f}"

        print(f"  t+{h+1:<3} | {str(target_ts):>18} | {predictions[h]:>14.2f} | {lower[h]:>10.2f} | {upper[h]:>10.2f} | {actual_str}")

    print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="10-hour solar power prediction")
    parser.add_argument("--data", type=str, default=None, help="Path to xlsx data file")
    parser.add_argument("--datetime", type=str, default=None,
                        help="Target datetime (e.g., '2026-03-14 12:00:00')")
    args = parser.parse_args()
    main(xlsx_path=args.data, target_datetime=args.datetime)
