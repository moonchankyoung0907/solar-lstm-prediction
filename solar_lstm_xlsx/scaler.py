"""MinMaxScaler 래퍼"""

import logging
import pathlib

import joblib
import numpy as np
from sklearn.preprocessing import MinMaxScaler

from solar_lstm_xlsx.config import SCALER_PATH

logger = logging.getLogger(__name__)


class SolarScaler:
    def __init__(self):
        self.x_scaler = MinMaxScaler()
        self.y_scaler = MinMaxScaler()
        self._fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray):
        n, seq, f = X.shape
        self.x_scaler.fit(X.reshape(-1, f))
        self.y_scaler.fit(y)
        self._fitted = True

    def transform_x(self, X: np.ndarray) -> np.ndarray:
        n, seq, f = X.shape
        return self.x_scaler.transform(X.reshape(-1, f)).reshape(n, seq, f)

    def transform_y(self, y: np.ndarray) -> np.ndarray:
        return self.y_scaler.transform(y)

    def inverse_y(self, y_scaled: np.ndarray) -> np.ndarray:
        return self.y_scaler.inverse_transform(y_scaled)

    def save(self, path=None):
        path = pathlib.Path(path) if path else SCALER_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"x_scaler": self.x_scaler, "y_scaler": self.y_scaler}, path)
        logger.info("Scaler saved to %s", path)

    def load(self, path=None):
        path = pathlib.Path(path) if path else SCALER_PATH
        data = joblib.load(path)
        self.x_scaler = data["x_scaler"]
        self.y_scaler = data["y_scaler"]
        self._fitted = True
        logger.info("Scaler loaded from %s", path)
