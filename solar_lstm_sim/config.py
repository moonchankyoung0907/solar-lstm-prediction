"""전체 설정 상수"""

import os

# ── DB ──────────────────────────────────────────────
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "shkim1224")
DB_NAME = os.getenv("DB_NAME", "solar_lstm")

# ── 태양광 시스템 ───────────────────────────────────
SYSTEM_CAPACITY_KW = 100          # 시스템 용량 (kW)
INVERTER_EFFICIENCY = 0.96        # 인버터 효율 η
PERFORMANCE_RATIO = 0.85          # 시스템 종합 성능비 PR
NOCT = 45                         # 공칭 동작 셀 온도 (℃)
LATITUDE = 35.1796                # 위도 (대전)
LONGITUDE = 129.0756              # 경도

# ── 시뮬레이터 노이즈 ──────────────────────────────
SENSOR_IRR_NOISE_RATIO = 0.05     # 센서 일사량 노이즈 ±5%
FORECAST_IRR_NOISE_STD = 50       # 예측 일사량 노이즈 σ (W/m²)
FORECAST_TEMP_NOISE_STD = 2       # 예측 기온 노이즈 σ (℃)
INVERTER_NOISE_RATIO = 0.03       # 인버터 효율 노이즈 ±3%
PEAK_IRRADIANCE = 1000            # 최대 일사량 (W/m²)

# 계절별 기준 기온 (℃)
SEASONAL_TEMP = {
    "spring": 15,   # 3-5월
    "summer": 30,   # 6-8월
    "autumn": 18,   # 9-11월
    "winter": 2,    # 12-2월
}

# ── LSTM 하이퍼파라미터 ─────────────────────────────
SEQ_LEN = 35                      # 24(과거) + 1(현재) + 10(미래)
PAST_STEPS = 24
CURRENT_STEPS = 1
FUTURE_STEPS = 10
NUM_FEATURES = 8                  # irr, temp, power, irr_fore, temp_fore, hour_sin, hour_cos, month_norm

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

# ── 경로 ────────────────────────────────────────────
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "model.keras"
SCALER_PATH = MODEL_DIR / "scaler.pkl"
HISTORY_DIR = MODEL_DIR / "model_history"

# ── 부트스트랩 ──────────────────────────────────────
BOOTSTRAP_DAYS = 90               # 초기 시뮬 데이터 일수

# ── 모니터링 ────────────────────────────────────────
MAPE_THRESHOLD = 10.0             # MAPE 임계치 (%)
CONFIDENCE_LOWER = 0.90           # 신뢰구간 하한 비율
CONFIDENCE_UPPER = 1.10           # 신뢰구간 상한 비율

# ── 이메일 (미설정시 로그만) ────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ALERT_RECIPIENT = os.getenv("ALERT_RECIPIENT", "")

# ── API ─────────────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = 8000
