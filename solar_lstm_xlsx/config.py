"""설정 상수"""

import pathlib

# ── 경로 ────────────────────────────────────────────
BASE_DIR = pathlib.Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "model.keras"
SCALER_PATH = MODEL_DIR / "scaler.pkl"
HISTORY_DIR = MODEL_DIR / "model_history"

DATA_PATH = BASE_DIR.parent / "train_log.xlsx"

# ── 태양광 시스템 ───────────────────────────────────
NOCT = 45  # 공칭 동작 셀 온도 (℃)

# ── LSTM 하이퍼파라미터 ─────────────────────────────
SEQ_LEN = 35          # 24(과거) + 1(현재) + 10(미래)
PAST_STEPS = 24
FUTURE_STEPS = 10
NUM_FEATURES = 8

LSTM_UNITS_1 = 128
LSTM_UNITS_2 = 64
DENSE_UNITS_1 = 32
DENSE_UNITS_2 = 16
DROPOUT_RATE = 0.2
LEARNING_RATE = 0.001
EPOCHS = 100
BATCH_SIZE = 32
EARLY_STOP_PATIENCE = 10
TRAIN_RATIO = 0.8

# ── 예측 ────────────────────────────────────────────
CONFIDENCE_LOWER = 0.90
CONFIDENCE_UPPER = 1.10
