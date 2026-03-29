"""학습 파이프라인 — 데이터 로드 → 전처리 → 윈도우 → 스케일 → 분할 → 학습 → 비교 → 저장"""

import logging
import shutil
from datetime import datetime

import numpy as np
import pandas as pd

from solar_lstm_sim.config import (
    TRAIN_RATIO,
    BOOTSTRAP_DAYS,
    MODEL_DIR,
    MODEL_PATH,
    SCALER_PATH,
    HISTORY_DIR,
)
from solar_lstm_sim.db.db_handler import DBHandler
from solar_lstm_sim.simulator.simulator import SolarSimulator
from solar_lstm_sim.pipeline.preprocessor import preprocess_sensor, validate_quality, REQUIRED_SENSOR_COLS
from solar_lstm_sim.pipeline.feature_builder import build_sliding_windows
from solar_lstm_sim.pipeline.scaler import SolarScaler
from solar_lstm_sim.pipeline.lstm_model import build_model, train_model, load_model, predict
from solar_lstm_sim.monitoring.evaluator import compute_mape

logger = logging.getLogger(__name__)


class LSTMTrainer:
    """LSTM 학습·재학습 관리"""

    def __init__(self):
        self.db = DBHandler()
        self.simulator = SolarSimulator()

    def bootstrap_if_needed(self):
        """DB가 비어있으면 90일 시뮬 데이터 생성 + 초기 학습"""
        count = self.db.get_sensor_count()
        if count > 0:
            logger.info("DB already has %d sensor rows. Skipping bootstrap.", count)
            return False

        logger.info("DB is empty. Bootstrapping %d days of simulated data...", BOOTSTRAP_DAYS)

        # 대량 데이터 생성
        sensor_rows, forecast_rows = self.simulator.generate_historical_data(days=BOOTSTRAP_DAYS)

        # DB에 bulk insert
        self.db.bulk_insert_sensor_data(sensor_rows)
        self.db.bulk_insert_forecast_data(forecast_rows)

        logger.info("Bootstrap data inserted. Starting initial training...")
        self.train()
        return True

    def train(self, days: int = BOOTSTRAP_DAYS) -> dict:
        """전체 학습 파이프라인"""
        # 1. 데이터 로드
        sensor_data = self.db.get_all_sensor_data(days=days)
        forecast_data = self.db.get_all_forecast_data(days=days)

        if len(sensor_data) < 100:
            logger.warning("Not enough sensor data (%d rows). Aborting training.", len(sensor_data))
            return {"status": "aborted", "reason": "insufficient data"}

        sensor_df = pd.DataFrame(sensor_data)
        forecast_df = pd.DataFrame(forecast_data)

        # 2. 전처리
        sensor_df = preprocess_sensor(sensor_df)
        if not validate_quality(sensor_df, REQUIRED_SENSOR_COLS):
            logger.error("Data quality check failed. Aborting training.")
            return {"status": "aborted", "reason": "quality check failed"}

        # 3. 슬라이딩 윈도우
        X, y = build_sliding_windows(sensor_df, forecast_df)
        if len(X) == 0:
            logger.warning("No sliding windows generated. Aborting training.")
            return {"status": "aborted", "reason": "no windows"}

        # 4. 스케일링
        scaler = SolarScaler()
        scaler.fit(X, y)

        X_scaled = scaler.transform_x(X)
        y_scaled = scaler.transform_y(y)

        # 5. 시계열 분할 (80/20, shuffle=False)
        split_idx = int(len(X_scaled) * TRAIN_RATIO)
        X_train, X_val = X_scaled[:split_idx], X_scaled[split_idx:]
        y_train, y_val = y_scaled[:split_idx], y_scaled[split_idx:]

        logger.info("Train: %d, Val: %d", len(X_train), len(X_val))

        # 6. 모델 빌드 + 학습 (임시 경로에 저장)
        candidate_path = MODEL_DIR / "model_candidate.keras"
        model = build_model()
        train_model(model, X_train, y_train, X_val, y_val, save_path=candidate_path)

        # 7. 검증 MAPE 계산 (신모델)
        y_val_pred_scaled = predict(model, X_val)
        y_val_pred = scaler.inverse_y(y_val_pred_scaled)
        y_val_actual = scaler.inverse_y(y_val)
        new_mape = compute_mape(y_val_actual.flatten(), y_val_pred.flatten())

        # 8. 기존 모델 비교 + 교체 판단
        adopted = True
        old_mape = float("inf")
        has_old_model = MODEL_PATH.exists()

        if has_old_model:
            try:
                old_model = load_model()
                y_old_pred_scaled = predict(old_model, X_val)
                y_old_pred = scaler.inverse_y(y_old_pred_scaled)
                old_mape = compute_mape(y_val_actual.flatten(), y_old_pred.flatten())

                if new_mape >= old_mape:
                    adopted = False
                    logger.info("New model MAPE %.2f%% >= old %.2f%%. Keeping old model.",
                                new_mape, old_mape)
            except Exception as e:
                logger.warning("Could not load old model for comparison: %s", e)

        # 9. 저장
        if adopted:
            # 기존 모델 백업
            if has_old_model:
                HISTORY_DIR.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = HISTORY_DIR / f"model_{ts}.keras"
                shutil.copy2(MODEL_PATH, backup_path)
                logger.info("Old model backed up to %s", backup_path)

            shutil.copy2(candidate_path, MODEL_PATH)
            scaler.save()
            logger.info("New model saved. MAPE: %.2f%%", new_mape)

        # 임시 파일 정리
        if candidate_path.exists():
            candidate_path.unlink()

        # 10. DB 로그
        self.db.insert_model_log(
            trained_at=datetime.now(),
            mape_new=round(new_mape, 4),
            mape_old=round(old_mape, 4) if old_mape != float("inf") else 0.0,
            adopted=adopted,
            model_path=str(MODEL_PATH) if adopted else "",
        )

        return {
            "status": "completed",
            "new_mape": round(new_mape, 4),
            "old_mape": round(old_mape, 4) if old_mape != float("inf") else None,
            "adopted": adopted,
            "train_samples": len(X_train),
            "val_samples": len(X_val),
        }
