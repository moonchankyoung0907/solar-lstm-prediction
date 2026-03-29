# Solar LSTM Prediction System - Conversation Thread

## Phase 1~5: 프로젝트 구조 및 핵심 모듈 구현

### Prompt 1
> Implement the following plan: [solar_lstm_simulation.md 기반 상세 구현 계획 - 11단계, 24파일]

**Response:**
- 프로젝트 구조 생성 (`solar_lstm_sim/` 패키지)
- `pyproject.toml` 작성 (tensorflow, numpy, pandas, fastapi 등 의존성)
- `config.py` — DB 설정, LSTM 하이퍼파라미터, 경로 상수
- `db/db_handler.py` — MySQL 5개 테이블 CRUD (sensor_data, forecast_data, prediction_result, error_log, model_log)
- `simulator/simulator.py` — SolarSimulator (sensor, forecast, inverter 시뮬레이터)
- `pipeline/preprocessor.py` — IQR 이상치 제거, 선형 보간, 야간 마스킹
- `pipeline/feature_builder.py` — (35, 8) 입력 텐서 빌더
- `pipeline/scaler.py` — MinMaxScaler 래퍼
- `pipeline/lstm_model.py` — LSTM 모델 빌드/학습/예측

---

### Prompt 2
> 계속작업진행해줘

**Response:**
- Phase 6~11 구현 완료
- `training/train_lstm.py` — LSTMTrainer (bootstrap + 학습)
- `pipeline/predict_pipeline.py` — PredictionPipeline
- `monitoring/evaluator.py` — MAPE, RMSE 평가
- `monitoring/notifier.py` — SMTP 알림
- `training/retrainer.py` — 일일 재학습
- `api/api_server.py` — FastAPI 서버 (/health, /predict, /simulate 등)
- `solar_lstm_sim/main.py` — 엔트리포인트 (bootstrap → APScheduler → uvicorn)
- `main.py` (root) — 실행 런처
- `uv sync` 실행 → 63개 패키지 설치 완료

---

## Phase: 첫 실행 및 버그 수정

### Prompt 3
> uv run solar_lstm_sim/main.py

**Response:**
- ModuleNotFoundError 발생
- `uv run python main.py`로 수정하여 실행
- 시스템 부트스트랩 성공 (2,160 sensor + 21,600 forecast 행)
- LSTM 학습 완료 (42 epochs, val_loss=0.000383, MAPE=5.77%)
- **버그 발견**: ModelCheckpoint가 MODEL_PATH에 직접 저장 → 모델 비교 시 동일 모델 비교됨 → adopted=False → 스케일러 미저장

---

### Prompt 4
> 계속작업진행해줘

**Response:**
- 학습 로직 수정: `model_candidate.keras` 임시 경로에 저장 후 기존 모델과 비교
- Clean DB로 재실행
- 학습 완료 (36 epochs, val_loss=0.000388, MAPE=4.79%)
- 모델 + 스케일러 정상 저장
- API 테스트 성공: /health, /simulate, /predict/run, /predict 모두 정상 동작

---

### Prompt 5
> 백그라운드에서 실행되는 것을 중지해줘

**Response:**
- TaskStop으로 백그라운드 프로세스 중지 완료

---

## Phase: 시스템 이해 및 설명

### Prompt 6
> solar_lstm_sim\main.py의 실행 프로세스를 자세히 설명해줘

**Response:**
- `start()` 함수 실행 흐름 상세 설명:
  1. `bootstrap_system()` — DB 연결, 테이블 생성, 90일 히스토리 생성, LSTM 최초 학습
  2. APScheduler 설정 — 매시 정각 예측, 매일 자정 재학습
  3. `uvicorn.run()` — FastAPI 서버 8000번 포트 시작

---

### Prompt 7
> lstm의 학습에 사용되는 첫번째 x, y의 값을 보여줘

**Response:**
- X[0]: (35×8) 텐서 표시 — 과거 24시간 + 현재 + 미래 10시간
- y[0]: 10개 목표값 (미래 10시간 발전량)

---

### Prompt 8
> lstm 의 학습을 위해 사용되는 입력 및 출력을 두개만 보여주고 뭔지 설명해 줄래?

**Response:**
- 첫 번째/두 번째 학습 샘플의 입력/출력 표시
- 8개 feature 설명, 35-step 시퀀스 구조 설명
- 슬라이딩 윈도우 방식의 데이터 생성 과정 설명

---

### Prompt 9
> 첫번 입력 출력 학습데이터의 feature값을 보여줘

**Response:**
- X[0]의 35×8 전체 값을 테이블 형태로 상세 표시
- 각 feature의 의미 설명 (irr_actual, temp_module, power_actual 등)

---

### Prompt 10
> 학습 입력의 feature 값이 0으로 된 것은 논리적으로 무슨 의미?

**Response:**
- **물리적 0 (Physical Zero)**: 야간 일사량=0, 발전량=0 → 실제 값
- **구조적 0 (Structural Zero)**: 과거 슬롯의 예보값=0 (N/A), 미래 슬롯의 실측값=0 (N/A)
- LSTM이 두 종류의 0을 구분 못하는 문제점 설명
- 해결 방안 제시: 마스크 feature, -1 채움, 별도 입력 구조

---

## Phase: 실행 방법 및 모델 활용

### Prompt 11
> 다 이해되었어. 어떻게 실행하면 되니?

**Response:**
- `python main.py` (루트 디렉토리에서 실행)
- 실행 시 bootstrap → scheduler → API 서버 순서 설명

---

### Prompt 12
> main.py는 solar_lstm_sim 폴더에 있는 것을 의미하니?

**Response:**
- 루트의 `main.py`를 의미함 (solar_lstm_sim/main.py가 아님)
- 루트 main.py → solar_lstm_sim.main.start() 호출 구조 설명

---

### Prompt 13
> [python main.py FileNotFoundError 에러 붙여넣기]

**Response:**
- 루트 main.py가 삭제된 상태 발견
- main.py 재생성 (3줄 런처 파일)

---

### Prompt 14
> python main.py [성공적인 시작 로그 붙여넣기]

**Response:**
- 기존 DB 데이터(2,185행)로 정상 시작 확인
- 부트스트랩 스킵, 스케줄러 시작, FastAPI 실행 확인

---

### Prompt 15
> 학습된 lstm 모델은 어디에 저장되니

**Response:**
- `solar_lstm_sim/models/` 폴더 구조 설명:
  - `model.keras` — 학습된 LSTM 모델
  - `scaler.pkl` — 입출력 스케일러
  - `model_history/` — 모델 버전 이력

---

### Prompt 16
> 학습된 모델을 사용하여 현재 시각을 기준으로 입력을 사용하여 10시간 태양광 발전 예측량을 보려면 어떻게 해야 하나

**Response:**
- `curl -X POST http://localhost:8000/predict/run` — 예측 실행
- `curl http://localhost:8000/predict` — 최근 예측 결과 조회

---

### Prompt 17
> 상기명령을 실행하면 Content에 10시간 발전량 예측량이 나오는데 이것만 깔끔하게 보려면

**Response:**
- curl + python 조합으로 테이블 형태 출력 명령어 제공

---

## Phase: log.xlsx 분석 및 train_log.xlsx 생성

### Prompt 18
> log.xlsx 파일을 분석해줘

**Response:**
- 2일간(2026-03-14, 03-15) 실제 태양광 발전소 데이터
- 48행, 12컬럼 (당일/익일 발전량, 일사량, 기온, 풍속)
- 3/14 맑은 날 (피크 1,964kW), 3/15 흐린 날 (피크 929kW)

---

### Prompt 19
> log.xlsx는 이틀간의 태양광발전 데이터와 기상청으로부터 예측된 값을 1일 24개씩 이틀간 저장한 데이터임. 나는 이것을 기반으로 2026-03-15일 이전으로 30일간의 데이터를 만들려고해. train_log.xlsx 파일로 만들어주는데, lstm 학습에 필요한 컬럼만 포함해서 만들어줘.

**Response:**
- 30일 학습 데이터 생성 (2026-02-13 ~ 2026-03-14)
- 720행 (30일 × 24시간) × 7컬럼
- 결정론적 사인파 기반 날씨 패턴 (7.3일 + 13.1일 주기)
- 맑은 날/흐린 날 보간, 계절 보정 (2월→3월 기온 +2.5℃, 일사량 85%→100%)
- `train_log.xlsx` 파일 생성 완료

---

## Phase: solar_lstm_xlsx 패키지 생성

### Prompt 20
> train_log.xlsx 를 갖고 이전에 니가 만들었던 학습 파이선소스를 사용하려고 하는데 니가 만든 파이선 실행 소스가 뭐지?

**Response:**
- `solar_lstm_sim/training/train_lstm.py` — 시뮬레이션 기반 학습 (MySQL)
- train_log.xlsx 사용하려면 별도 xlsx 전용 파이프라인 필요

---

### Prompt 21
> 그래 그런데 이전에 니가 만든 solar_lstm_sim 을 변경하지 않고 다른 폴더에 train_log.xlsx를 사용하는 소스를 다시 만들어 줄래. solar_lstm_xlsx 폴더에

**Response:**
- `solar_lstm_xlsx/` 패키지 8개 파일 생성:
  - `config.py` — 설정 상수
  - `data_loader.py` — Excel 로더 (컬럼 매핑, NOCT 모듈온도 계산)
  - `preprocessor.py` — IQR 이상치 제거, 보간, 야간 마스킹
  - `feature_builder.py` — (35, 8) 슬라이딩 윈도우 빌더
  - `scaler.py` — MinMaxScaler 래퍼
  - `lstm_model.py` — LSTM 모델 (동일 아키텍처)
  - `train.py` — 학습 스크립트
  - `predict.py` — 예측 스크립트

---

### Prompt 22
> 니가 순서대로 실행해줘

**Response:**
- `train.py` 실행 → 학습 완료 (MAPE 24.47%)
- `predict.py` 실행 → 2026-03-14 12:00:00 기준 10시간 예측 결과 표시
- 예측값 vs 실측값 비교 테이블 출력

---

## Phase: xlsx 기반 학습 데이터 분석

### Prompt 23
> lstm의 학습에 사용되는 첫번째 입력과 출력을 보여줘

**Response:**
- X shape: (686, 35, 8), y shape: (686, 10)
- **X[0]** — 기준 시각: 2026-02-14 00:00:00 (자정)
  - idx 0~23 (t-24~t-1): 2/13 하루 실측 — 낮 피크 irr=489, power=1,363kW → 야간 0
  - idx 24 (t=0): 자정, 모든 값 0 (temp=-1.0℃)
  - idx 25~34 (t+1~t+10): 미래 예보 — irr_forecast/temp_forecast만 값 있음
- **y[0]** — 미래 10시간 실측 발전량:
  - t+1~t+7 (01~07시): 0 kW (야간)
  - t+8 (08시): 249.81 kW
  - t+9 (09시): 627.85 kW
  - t+10 (10시): 974.30 kW

---

### Prompt 24 (현재 세션)
> lstm의 학습에 사용되는 첫번째 입력과 출력을 보여줘

**Response:**
- 동일한 결과 재확인 (세션 복구 후)
- X[0]: 35×8 전체 테이블 출력, y[0]: 10개 타겟값 출력

---

## 생성된 파일 목록

### Package 1: `solar_lstm_sim/` (시뮬레이션 기반, MySQL)
```
solar_lstm_sim/
├── __init__.py
├── config.py
├── main.py
├── db/
│   ├── __init__.py
│   └── db_handler.py
├── simulator/
│   ├── __init__.py
│   └── simulator.py
├── pipeline/
│   ├── __init__.py
│   ├── preprocessor.py
│   ├── feature_builder.py
│   ├── scaler.py
│   ├── lstm_model.py
│   └── predict_pipeline.py
├── training/
│   ├── __init__.py
│   ├── train_lstm.py
│   └── retrainer.py
├── monitoring/
│   ├── __init__.py
│   ├── evaluator.py
│   └── notifier.py
├── api/
│   ├── __init__.py
│   └── api_server.py
└── models/
    ├── model.keras
    ├── scaler.pkl
    └── model_history/
```

### Package 2: `solar_lstm_xlsx/` (Excel 기반)
```
solar_lstm_xlsx/
├── __init__.py
├── config.py
├── data_loader.py
├── preprocessor.py
├── feature_builder.py
├── scaler.py
├── lstm_model.py
├── train.py
├── predict.py
└── models/
    ├── model.keras
    └── scaler.pkl
```

### 기타 파일
```
main.py              # 루트 런처
pyproject.toml       # 프로젝트 의존성
log.xlsx             # 실제 2일간 태양광 데이터
train_log.xlsx       # 생성된 30일 학습 데이터
```

## 주요 에러 및 해결

| # | 에러 | 원인 | 해결 |
|---|------|------|------|
| 1 | ModuleNotFoundError | `uv run solar_lstm_sim/main.py` 직접 실행 | `uv run python main.py` 사용 |
| 2 | 모델 자기 비교 버그 | ModelCheckpoint → MODEL_PATH 직접 저장 | `model_candidate.keras` 임시 경로 사용 |
| 3 | ModuleNotFoundError | `python solar_lstm_sim\main.py` 패키지 경로 문제 | `sys.path.insert()` 추가 |
| 4 | FileNotFoundError | 루트 main.py 삭제됨 | main.py 재생성 |
| 5 | UnicodeEncodeError (cp949) | Windows 한글 인코딩 | `PYTHONIOENCODING=utf-8`, `-Xutf8` |
| 6 | openpyxl 미설치 | pandas xlsx 읽기 의존성 | `uv pip install openpyxl` |
