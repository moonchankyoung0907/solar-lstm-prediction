"""학습 파이프라인 — train_log.xlsx → LSTM 모델 학습"""

import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import numpy as np

from solar_lstm_xlsx.config import TRAIN_RATIO, MODEL_PATH, MODEL_DIR
from solar_lstm_xlsx.data_loader import load_xlsx
from solar_lstm_xlsx.preprocessor import preprocess
from solar_lstm_xlsx.feature_builder import build_sliding_windows
from solar_lstm_xlsx.scaler import SolarScaler
from solar_lstm_xlsx.lstm_model import build_model, train_model, predict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def compute_mape(actual, predicted):
    actual = np.asarray(actual, dtype=np.float64).flatten()
    predicted = np.asarray(predicted, dtype=np.float64).flatten()
    mask = actual != 0
    if mask.sum() == 0:
        return 0.0
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


def main(xlsx_path=None):
    logger.info("===== LSTM Training from xlsx =====")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 데이터 로드
    df = load_xlsx(xlsx_path)

    # 2. 전처리
    df = preprocess(df)

    # 3. 슬라이딩 윈도우
    X, y = build_sliding_windows(df)
    if len(X) == 0:
        logger.error("No sliding windows generated. Aborting.")
        return

    logger.info("X: %s, y: %s", X.shape, y.shape)

    # 4. 스케일링
    scaler = SolarScaler()
    scaler.fit(X, y)
    X_scaled = scaler.transform_x(X)
    y_scaled = scaler.transform_y(y)

    # 5. 시계열 분할 (80/20)
    split = int(len(X_scaled) * TRAIN_RATIO)
    X_train, X_val = X_scaled[:split], X_scaled[split:]
    y_train, y_val = y_scaled[:split], y_scaled[split:]
    logger.info("Train: %d, Val: %d", len(X_train), len(X_val))

    # 6. 모델 빌드 + 학습
    model = build_model()
    train_model(model, X_train, y_train, X_val, y_val)

    # 7. 검증 MAPE
    y_pred_scaled = predict(model, X_val)
    y_pred = scaler.inverse_y(y_pred_scaled)
    y_actual = scaler.inverse_y(y_val)
    mape = compute_mape(y_actual.flatten(), y_pred.flatten())
    logger.info("Validation MAPE: %.2f%%", mape)

    # 8. 저장
    model.save(str(MODEL_PATH))
    scaler.save()
    logger.info("Model saved to %s", MODEL_PATH)

    # 9. 샘플 예측 출력
    print()
    print("=" * 70)
    print(f"  Training Complete | MAPE: {mape:.2f}%")
    print(f"  Model: {MODEL_PATH}")
    print("=" * 70)
    print()
    print("  Sample prediction (last validation window):")
    print(f"  {'hour':>6} | {'actual(kW)':>12} | {'predicted(kW)':>14} | {'error':>8}")
    print(f"  {'-'*50}")
    for h in range(10):
        a = y_actual[-1, h]
        p = y_pred[-1, h]
        err = abs(a - p)
        print(f"  t+{h+1:<3} | {a:>12.2f} | {p:>14.2f} | {err:>8.2f}")


if __name__ == "__main__":
    main()
