"""평가 지표 — MAPE, RMSE 계산"""

import numpy as np


def compute_mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean Absolute Percentage Error (%)

    actual 이 0인 경우 해당 샘플은 제외
    """
    actual = np.asarray(actual, dtype=np.float64).flatten()
    predicted = np.asarray(predicted, dtype=np.float64).flatten()

    mask = actual != 0
    if mask.sum() == 0:
        return 0.0

    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


def compute_rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Root Mean Squared Error"""
    actual = np.asarray(actual, dtype=np.float64).flatten()
    predicted = np.asarray(predicted, dtype=np.float64).flatten()
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))
