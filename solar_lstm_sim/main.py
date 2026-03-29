"""메인 스케줄러 — 부트스트랩 + APScheduler(매시간/매일) + FastAPI"""

import sys
from pathlib import Path

# 직접 실행(python solar_lstm_sim/main.py) 지원
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
import uvicorn

from solar_lstm_sim.config import API_HOST, API_PORT, MODEL_DIR, HISTORY_DIR
from solar_lstm_sim.db.db_handler import DBHandler
from solar_lstm_sim.training.train_lstm import LSTMTrainer
from solar_lstm_sim.pipeline.predict_pipeline import PredictionPipeline
from solar_lstm_sim.training.retrainer import retrain_job
from solar_lstm_sim.api.api_server import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def hourly_job():
    """매시간 정각 실행 — 예측 파이프라인"""
    logger.info("--- Hourly prediction job triggered ---")
    pipeline = PredictionPipeline()
    result = pipeline.run()
    logger.info("Hourly job result: %s", result.get("status"))


def bootstrap_system():
    """시스템 초기화: DB 생성 + 테이블 생성 + 디렉토리 + 부트스트랩"""
    # 디렉토리 생성
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    # DB 초기화
    db = DBHandler()
    db.create_database()
    db.create_tables()

    # 부트스트랩 (DB 비어있으면 90일 시뮬 데이터 생성 + 초기 학습)
    trainer = LSTMTrainer()
    trainer.bootstrap_if_needed()


def start():
    """메인 진입점"""
    logger.info("========== Solar LSTM Prediction System Starting ==========")

    # 1. 부트스트랩
    bootstrap_system()

    # 2. APScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(hourly_job, "cron", minute=0, id="hourly_predict")
    scheduler.add_job(retrain_job, "cron", hour=0, minute=0, id="daily_retrain")
    scheduler.start()
    logger.info("Scheduler started. Hourly: predict, Daily 00:00: retrain")

    # 3. FastAPI (blocking)
    logger.info("Starting FastAPI on %s:%d", API_HOST, API_PORT)
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")


if __name__ == "__main__":
    start()
