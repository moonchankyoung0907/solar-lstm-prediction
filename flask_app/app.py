"""Flask 웹앱 — LSTM 태양광 발전량 10시간 예측"""

import sys
import logging
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from flask import Flask, render_template, request, jsonify

from solar_lstm_xlsx.data_loader import load_xlsx
from solar_lstm_xlsx.preprocessor import preprocess
from solar_lstm_xlsx.feature_builder import build_single_input
from solar_lstm_xlsx.scaler import SolarScaler
from solar_lstm_xlsx.lstm_model import load_model, predict
from solar_lstm_xlsx.config import MODEL_PATH, SCALER_PATH, FUTURE_STEPS, CONFIDENCE_LOWER, CONFIDENCE_UPPER

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── 앱 시작 시 데이터·모델 로드 ─────────────────────────
logger.info("Loading data and model...")

DATA_PATH = ROOT / "train_log.xlsx"
df_global = load_xlsx(str(DATA_PATH))
df_global = preprocess(df_global)

model_global = load_model()
scaler_global = SolarScaler()
scaler_global.load()

DATE_MIN = df_global["timestamp"].min()
DATE_MAX = df_global["timestamp"].max()

logger.info("Data range: %s ~ %s", DATE_MIN, DATE_MAX)
logger.info("Model and scaler loaded.")


def run_prediction(target_datetime: str):
    """target_datetime 기준으로 10시간 예측 수행 → dict 반환"""
    target_ts = pd.Timestamp(target_datetime)

    idx_series = df_global[df_global["timestamp"] == target_ts].index
    if len(idx_series) == 0:
        return None, f"데이터에 해당 시각이 없습니다: {target_ts}\n데이터 범위: {DATE_MIN} ~ {DATE_MAX}"

    current_idx = idx_series[0]

    # 입력 텐서 구성 → 스케일링 → 예측 → 역정규화
    X = build_single_input(df_global, current_idx)
    X_scaled = scaler_global.transform_x(X)
    y_pred_scaled = predict(model_global, X_scaled)
    y_pred = scaler_global.inverse_y(y_pred_scaled)
    y_pred = np.clip(y_pred, 0, None)[0]  # (10,)

    lower = y_pred * CONFIDENCE_LOWER
    upper = y_pred * CONFIDENCE_UPPER

    rows = []
    for h in range(FUTURE_STEPS):
        target_idx = current_idx + 1 + h
        future_ts = target_ts + pd.Timedelta(hours=h + 1)

        actual = None
        abs_err = None
        mape = None
        if target_idx < len(df_global):
            actual = float(df_global.iloc[target_idx]["power_actual"])
            abs_err = abs(y_pred[h] - actual)
            if actual > 0:
                mape = abs_err / actual * 100

        rows.append({
            "hour": f"t+{h+1}",
            "target_time": future_ts.strftime("%Y-%m-%d %H:%M"),
            "predicted": round(float(y_pred[h]), 2),
            "lower": round(float(lower[h]), 2),
            "upper": round(float(upper[h]), 2),
            "actual": round(actual, 2) if actual is not None else None,
            "abs_err": round(float(abs_err), 2) if abs_err is not None else None,
            "mape": round(float(mape), 2) if mape is not None else None,
        })

    # 전체 MAPE (야간 0 제외)
    valid = [r for r in rows if r["mape"] is not None]
    overall_mape = round(sum(r["mape"] for r in valid) / len(valid), 2) if valid else None

    return {
        "base_time": target_ts.strftime("%Y-%m-%d %H:%M"),
        "rows": rows,
        "overall_mape": overall_mape,
    }, None


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None
    form_values = {
        "year": "",
        "month": "",
        "day": "",
        "hour": "",
    }

    if request.method == "POST":
        try:
            year = int(request.form["year"])
            month = int(request.form["month"])
            day = int(request.form["day"])
            hour = int(request.form["hour"])

            form_values = {"year": year, "month": month, "day": day, "hour": hour}
            target_dt = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:00:00"
            result, error = run_prediction(target_dt)
        except (ValueError, KeyError) as e:
            error = f"입력값 오류: {e}"

    return render_template(
        "index.html",
        result=result,
        error=error,
        form_values=form_values,
        date_min=DATE_MIN.strftime("%Y-%m-%d %H:%M"),
        date_max=DATE_MAX.strftime("%Y-%m-%d %H:%M"),
    )


@app.route("/api/predict", methods=["GET"])
def api_predict():
    """REST API: ?datetime=2026-03-14+12:00:00"""
    dt_str = request.args.get("datetime")
    if not dt_str:
        return jsonify({"error": "datetime 파라미터가 필요합니다."}), 400
    result, error = run_prediction(dt_str)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
