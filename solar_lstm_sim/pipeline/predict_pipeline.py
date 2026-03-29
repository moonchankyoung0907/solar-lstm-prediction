"""매시간 예측 파이프라인"""

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from solar_lstm_sim.config import (
    MODEL_PATH,
    SCALER_PATH,
    FUTURE_STEPS,
    CONFIDENCE_LOWER,
    CONFIDENCE_UPPER,
    MAPE_THRESHOLD,
    PAST_STEPS,
)
from solar_lstm_sim.db.db_handler import DBHandler
from solar_lstm_sim.simulator.simulator import SolarSimulator
from solar_lstm_sim.pipeline.preprocessor import preprocess_sensor, validate_quality, REQUIRED_SENSOR_COLS
from solar_lstm_sim.pipeline.feature_builder import build_single_input
from solar_lstm_sim.pipeline.scaler import SolarScaler
from solar_lstm_sim.pipeline.lstm_model import load_model, predict
from solar_lstm_sim.monitoring.evaluator import compute_mape, compute_rmse
from solar_lstm_sim.monitoring.notifier import send_alert

logger = logging.getLogger(__name__)


class PredictionPipeline:
    """매시간 실행되는 예측 파이프라인"""

    def __init__(self):
        self.db = DBHandler()
        self.simulator = SolarSimulator()

    def run(self) -> dict:
        """전체 예측 파이프라인 실행"""
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        logger.info("=== Prediction pipeline started at %s ===", now)

        try:
            # 1. 시뮬레이터 호출 + DB 저장
            sensor = self.simulator.sensor_simulator(now)
            self.db.insert_sensor_data(**sensor)

            forecasts = self.simulator.forecast_simulator(now)
            for fc in forecasts:
                self.db.insert_forecast_data(**fc)

            # 2. DB에서 과거 24시간 로드
            past_data = self.db.get_sensor_data(hours=PAST_STEPS, before=now - timedelta(hours=1))
            if len(past_data) < PAST_STEPS:
                logger.warning("Only %d past records (need %d). Proceeding with available data.",
                               len(past_data), PAST_STEPS)

            past_df = pd.DataFrame(past_data)

            # 3. 전처리
            if len(past_df) > 0:
                past_df = preprocess_sensor(past_df)
                if not validate_quality(past_df, REQUIRED_SENSOR_COLS):
                    send_alert("Data quality check failed", f"Prediction at {now} aborted due to quality issues.")
                    return {"status": "aborted", "reason": "quality check failed"}

            # 4. 모델/스케일러 로드
            if not MODEL_PATH.exists() or not SCALER_PATH.exists():
                logger.error("Model or scaler not found. Run training first.")
                return {"status": "aborted", "reason": "model not found"}

            model = load_model()
            scaler = SolarScaler()
            scaler.load()

            # 5. 입력 텐서 구성
            X = build_single_input(past_df, sensor, forecasts)

            # 6. 스케일링 + 예측
            X_scaled = scaler.transform_x(X)
            y_pred_scaled = predict(model, X_scaled)
            y_pred = scaler.inverse_y(y_pred_scaled)
            y_pred = np.clip(y_pred, 0, None)  # 음수 방지

            predictions = y_pred[0]  # shape (10,)

            # 7. 신뢰구간
            lower = predictions * CONFIDENCE_LOWER
            upper = predictions * CONFIDENCE_UPPER

            # 8. DB 저장
            for i in range(FUTURE_STEPS):
                target_time = now + timedelta(hours=i + 1)
                self.db.insert_prediction(
                    created_at=now,
                    target_time=target_time,
                    power_lstm=round(float(predictions[i]), 4),
                    confidence_lower=round(float(lower[i]), 4),
                    confidence_upper=round(float(upper[i]), 4),
                )

            # 9. 이전 예측 평가
            self._evaluate_previous(now)

            logger.info("Prediction complete. Forecast: %s", predictions.round(2).tolist())
            return {
                "status": "success",
                "timestamp": now.isoformat(),
                "predictions": predictions.round(4).tolist(),
            }

        except Exception as e:
            logger.exception("Prediction pipeline error: %s", e)
            return {"status": "error", "reason": str(e)}

    def _evaluate_previous(self, now: datetime):
        """이전 예측 vs 현재 실측 비교"""
        try:
            # 1시간 전에 만든 예측 중 target_time=now인 것
            prev_preds = self.db.get_predictions_for_evaluation(target_time=now)
            if not prev_preds:
                return

            actual_sensor = self.db.get_latest_sensor()
            if not actual_sensor:
                return

            power_actual = actual_sensor["power_actual"]
            power_predicted = prev_preds[0]["power_lstm"]

            if power_actual is None or power_predicted is None:
                return

            mape = compute_mape(
                np.array([power_actual]),
                np.array([power_predicted]),
            )
            rmse = compute_rmse(
                np.array([power_actual]),
                np.array([power_predicted]),
            )

            self.db.insert_error_log(
                timestamp=now,
                power_predicted=power_predicted,
                power_actual=power_actual,
                mape=round(mape, 4),
                rmse=round(rmse, 4),
            )

            if mape > MAPE_THRESHOLD:
                send_alert(
                    "MAPE threshold exceeded",
                    f"MAPE={mape:.2f}% at {now}. Predicted={power_predicted:.2f}, Actual={power_actual:.2f}"
                )

        except Exception as e:
            logger.warning("Evaluation error: %s", e)
