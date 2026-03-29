"""재학습 트리거 — 매일 자정 호출"""

import logging

from solar_lstm_sim.training.train_lstm import LSTMTrainer

logger = logging.getLogger(__name__)


def retrain_job():
    """매일 자정 재학습"""
    logger.info("=== Daily retraining job started ===")
    trainer = LSTMTrainer()
    result = trainer.train(days=90)
    logger.info("Retraining result: %s", result)
    return result
