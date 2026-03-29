"""MinMaxScaler 래퍼 — fit / transform / inverse / save / load"""

import logging
import pathlib

import joblib
import numpy as np
from sklearn.preprocessing import MinMaxScaler

from solar_lstm_sim.config import SCALER_PATH, NUM_FEATURES, FUTURE_STEPS

logger = logging.getLogger(__name__)


class SolarScaler:
    """입력(X) 스케일러 + 출력(y) 스케일러"""

    def __init__(self):
        self.x_scaler = MinMaxScaler()
        self.y_scaler = MinMaxScaler()
        self._fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray):
        """X: (N, SEQ_LEN, F), y: (N, 10) — 학습 데이터 기준으로 fit"""
        n, seq, f = X.shape
        X_flat = X.reshape(-1, f)
        self.x_scaler.fit(X_flat)

        self.y_scaler.fit(y)
        self._fitted = True
        logger.info("Scaler fitted on %d samples.", n)

    def transform_x(self, X: np.ndarray) -> np.ndarray:
        n, seq, f = X.shape
        X_flat = X.reshape(-1, f)
        X_scaled = self.x_scaler.transform(X_flat)
        return X_scaled.reshape(n, seq, f)

    def transform_y(self, y: np.ndarray) -> np.ndarray:
        return self.y_scaler.transform(y)

    def inverse_y(self, y_scaled: np.ndarray) -> np.ndarray:
        return self.y_scaler.inverse_transform(y_scaled)

    def save(self, path: pathlib.Path | str | None = None):
        path = pathlib.Path(path) if path else SCALER_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"x_scaler": self.x_scaler, "y_scaler": self.y_scaler}, path)
        logger.info("Scaler saved to %s", path)

    def load(self, path: pathlib.Path | str | None = None):
        path = pathlib.Path(path) if path else SCALER_PATH
        data = joblib.load(path)
        self.x_scaler = data["x_scaler"]
        self.y_scaler = data["y_scaler"]
        self._fitted = True
        logger.info("Scaler loaded from %s", path)

    @property
    def is_fitted(self) -> bool:
        return self._fitted
