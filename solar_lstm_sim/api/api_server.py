"""FastAPI — 예측 결과 조회 API"""

import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException

from solar_lstm_sim.db.db_handler import DBHandler
from solar_lstm_sim.pipeline.predict_pipeline import PredictionPipeline
from solar_lstm_sim.simulator.simulator import SolarSimulator

logger = logging.getLogger(__name__)

app = FastAPI(title="Solar LSTM Prediction API", version="1.0.0")
db = DBHandler()


@app.get("/health")
def health():
    """헬스 체크"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/predict")
def get_predict():
    """최신 10시간 예측 결과 조회"""
    predictions = db.get_latest_predictions()
    if not predictions:
        raise HTTPException(status_code=404, detail="No predictions available yet.")
    return {
        "status": "ok",
        "count": len(predictions),
        "predictions": [
            {
                "target_time": str(p["target_time"]),
                "power_lstm": p["power_lstm"],
                "confidence_lower": p["confidence_lower"],
                "confidence_upper": p["confidence_upper"],
            }
            for p in predictions
        ],
    }


@app.get("/metrics")
def get_metrics():
    """최신 MAPE, RMSE 조회"""
    metrics = db.get_latest_metrics()
    if not metrics:
        raise HTTPException(status_code=404, detail="No metrics available yet.")
    return {
        "status": "ok",
        "timestamp": str(metrics["timestamp"]),
        "mape": metrics["mape"],
        "rmse": metrics["rmse"],
        "power_predicted": metrics["power_predicted"],
        "power_actual": metrics["power_actual"],
    }


@app.get("/simulate")
def get_simulate():
    """현재 시뮬 데이터 생성 조회"""
    sim = SolarSimulator()
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    sensor = sim.sensor_simulator(now)
    forecasts = sim.forecast_simulator(now)
    return {
        "status": "ok",
        "sensor": {
            "timestamp": str(sensor["timestamp"]),
            "irradiance": sensor["irradiance"],
            "temp_module": sensor["temp_module"],
            "temp_air": sensor["temp_air"],
            "power_actual": sensor["power_actual"],
        },
        "forecasts": [
            {
                "forecast_time": str(f["forecast_time"]),
                "irradiance_forecast": f["irradiance_forecast"],
                "temp_forecast": f["temp_forecast"],
                "horizon": f["horizon"],
            }
            for f in forecasts
        ],
    }


@app.post("/predict/run")
def run_predict():
    """수동 예측 실행"""
    pipeline = PredictionPipeline()
    result = pipeline.run()
    return result
