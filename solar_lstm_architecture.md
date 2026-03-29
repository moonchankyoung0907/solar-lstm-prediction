# LSTM 기반 태양광발전소 10시간 발전량 예측 시스템

> 공공데이터 기상 예측(10시간) + 현장 센서 실측값 → LSTM 모델 → 10시간 후 발전량 예측

---

## 1. 전체 시스템 블록도

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart TD
    subgraph PUBLIC["🌐 공공데이터 (기상청 API)"]
        P1["일사량 예측\nt+1 ~ t+10 (W/m²)"]
        P2["기온 예측\nt+1 ~ t+10 (℃)"]
    end

    subgraph SENSOR["📡 현장 센서 (실시간)"]
        S1["일사량계\n현재 W/m²"]
        S2["온도 센서\n현재 모듈온도 ℃"]
    end

    subgraph FEATURE["🔧 feature_builder.py\n입력 특성 구성"]
        F1["현재 실측값\n일사량, 기온 (t=0)"]
        F2["10시간 예측값\n일사량, 기온 (t+1~t+10)"]
        F3["시간 특성\nhour, month, sin/cos 인코딩"]
        F4["과거 이력\n과거 24시간 실측 시퀀스\n(DB에서 로드)"]
    end

    subgraph LSTM_BLOCK["🧠 LSTM 예측 모델 (lstm_model.py)"]
        L1["입력 시퀀스 구성\nshape: (batch, seq_len, features)"]
        L2["LSTM Layer 1\nunits=128, return_sequences=True"]
        L3["Dropout 0.2"]
        L4["LSTM Layer 2\nunits=64, return_sequences=False"]
        L5["Dropout 0.2"]
        L6["Dense Layer\nunits=32, activation=relu"]
        L7["출력층\nunits=10 → t+1~t+10 발전량"]
    end

    subgraph OUTPUT["📤 예측 결과"]
        O2["역정규화\nScaler.inverse_transform()"]
        O1["10시간 발전량 예측\n단위: kW\nt+1 ~ t+10"]
    end

    subgraph DB["🗄️ MySQL (db_handler.py)"]
        DB1["sensor_data\n실측 이력 저장"]
        DB2["forecast_data\nAPI 예측값 저장"]
        DB3["prediction_result\n예측 결과 저장"]
    end

    %% 주 데이터 흐름 (실선)
    P1 & P2 --> F2
    S1 & S2 --> F1
    F1 & F2 & F3 & F4 --> L1
    DB1 -->|"과거 24시간"| F4
    L1 --> L2 --> L3 --> L4 --> L5 --> L6 --> L7
    L7 --> O2 --> O1

    %% DB 저장 경로 (점선)
    S1 & S2 -.-> DB1
    P1 & P2 -.-> DB2
    O1 -.-> DB3

    style PUBLIC fill:#e8f4f8,stroke:#0d6efd
    style SENSOR fill:#e8f8e8,stroke:#198754
    style LSTM_BLOCK fill:#f3e8ff,stroke:#6f42c1
    style OUTPUT fill:#fff3cd,stroke:#ffc107
```

---

## 2. LSTM 입력 시퀀스 구성 상세

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart LR
    subgraph SEQ["입력 시퀀스 구성 (seq_len = 34)"]
        direction TB
        PAST["과거 24시간 실측\n(t-24 ~ t-1)\n각 스텝: irr, temp, power\n→ shape: 24 × 3"]
        CURR["현재 실측 (t=0)\nirr_now, temp_now, power_now\n→ shape: 1 × 3"]
        FORE["미래 10시간 예측\n(t+1 ~ t+10)\nirr_fore, temp_fore\n→ shape: 10 × 2"]
    end

    subgraph CONCAT["통합 입력 텐서"]
        TENSOR["Zero-padding으로 차원 통일\nshape: (batch, 34, 8)\n\n8개 features:\n① irr_actual\n② temp_actual\n③ power_actual\n④ irr_forecast\n⑤ temp_forecast\n⑥ hour_sin\n⑦ hour_cos\n⑧ month_norm"]
    end

    subgraph TARGET["출력 (Target)"]
        OUT["t+1 ~ t+10 발전량\nshape: (batch, 10)\n단위: kW (정규화)"]
    end

    PAST & CURR & FORE --> TENSOR
    TENSOR --> OUT

    style TENSOR fill:#f3e8ff
    style OUT fill:#d4edda
```

---

## 3. LSTM 모델 아키텍처

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart TD
    IN["입력층\nInput shape: (34, 8)\n34 타임스텝 × 8 features"]

    subgraph LSTM1["LSTM Block 1"]
        L1A["LSTM Layer\nunits = 128\nreturn_sequences = True"]
        L1B["Dropout\nrate = 0.2"]
    end

    subgraph LSTM2["LSTM Block 2"]
        L2A["LSTM Layer\nunits = 64\nreturn_sequences = False"]
        L2B["Dropout\nrate = 0.2"]
    end

    subgraph DENSE["Dense Block"]
        D1["Dense Layer\nunits = 32\nactivation = ReLU"]
        D2["Dense Layer\nunits = 16\nactivation = ReLU"]
    end

    OUT["출력층\nDense(10, activation=linear)\n→ t+1 ~ t+10 발전량 예측"]

    LOSS["손실함수\nMSE Loss\nOptimizer: Adam (lr=0.001)"]
    METRIC["평가지표\nMAE, MAPE, RMSE"]

    IN --> L1A --> L1B --> L2A --> L2B --> D1 --> D2 --> OUT
    OUT --> LOSS & METRIC

    style IN fill:#e8f4f8
    style OUT fill:#d4edda
    style LOSS fill:#fff3cd
```

---

## 4. 데이터 흐름 및 처리 파이프라인

```mermaid
sequenceDiagram
    participant API as 공공데이터 API
    participant SEN as 현장 센서
    participant DB as MySQL DB
    participant FE as feature_builder.py
    participant SC as scaler.py
    participant LSTM as lstm_model.py
    participant EV as evaluator.py

    Note over API,EV: 매시간 정각 실행 (APScheduler)

    API ->> DB: 10시간 예측값 저장 (irr_fore, temp_fore)
    SEN ->> DB: 현재 실측값 저장 (irr_now, temp_now, power_now)

    DB ->> FE: 과거 24시간 실측 이력 로드
    DB ->> FE: 현재 실측값 로드
    DB ->> FE: 10시간 예측값 로드

    FE ->> FE: 시간 특성 생성 (sin/cos 인코딩)
    FE ->> SC: 원시 데이터 정규화 (MinMaxScaler)
    SC ->> FE: 정규화된 시퀀스 반환
    FE ->> LSTM: 입력 텐서 전달 shape:(1, 34, 8)

    LSTM ->> LSTM: 순전파 예측
    LSTM ->> SC: 예측값 역정규화
    SC ->> DB: 예측 결과 저장 (t+1~t+10, kW)

    DB ->> EV: 이전 예측값 vs 실측값 비교
    EV ->> EV: MAPE, RMSE 계산
    EV ->> DB: 오차 기록 저장
```

---

## 5. 학습 파이프라인 (train_lstm.py)

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart TD
    START["train_lstm.py 실행\n(초기 or 매일 자정 재학습)"]

    LOAD["DB에서 학습 데이터 로드\n과거 90일 실측 + 예측 이력"]

    CLEAN["데이터 전처리\n· 야간 데이터 제외\n· 이상치 제거 IQR\n· 결측값 보간"]

    FE["슬라이딩 윈도우 생성\nwindow_size = 34\nstep = 1\n→ 다수의 (X, y) 샘플 생성"]

    SCALE["정규화\nMinMaxScaler fit\nscaler.pkl 저장"]

    SPLIT["시계열 분할\nTrain 80% / Val 20%\n(시간 순서 유지, shuffle=False)"]

    BUILD["LSTM 모델 빌드\nKeras Sequential"]

    TRAIN["모델 학습\nepochs = 100\nbatch_size = 32\nEarlyStopping(patience=10)\nModelCheckpoint 저장"]

    EVAL{"검증 MAPE\n< 기존 모델?"}

    SAVE["model.keras 교체\nscaler.pkl 교체\nmodel_history/ 백업"]

    KEEP["기존 모델 유지\n로그만 기록"]

    LOG["model_log 테이블\n결과 DB 저장"]

    START --> LOAD --> CLEAN --> FE --> SCALE --> SPLIT --> BUILD --> TRAIN --> EVAL
    EVAL -->|"Yes"| SAVE
    EVAL -->|"No"| KEEP
    SAVE & KEEP --> LOG

    style EVAL fill:#fff3cd
    style SAVE fill:#d4edda
    style KEEP fill:#e2e3e5
```

---

## 6. 슬라이딩 윈도우 데이터셋 생성

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart LR
    subgraph RAW["원시 시계열 데이터 (시간순)"]
        R1["t=1"]
        R2["t=2"]
        R3["..."]
        R25["t=25"]
        R26["t=26"]
        R27["..."]
        R35["t=35"]
    end

    subgraph W1["샘플 #1"]
        X1["X: t=1~34\nshape:(34,8)"]
        Y1["y: t=35\npower kW"]
    end

    subgraph W2["샘플 #2"]
        X2["X: t=2~35\nshape:(34,8)"]
        Y2["y: t=36\npower kW"]
    end

    subgraph WN["샘플 #N (10시간 예측)"]
        XN["X: t=N~N+33\nshape:(34,8)"]
        YN["y: t+1~t+10\nshape:(10,) kW"]
    end

    RAW --> W1 & W2 & WN

    style W1 fill:#e8f4f8
    style W2 fill:#e8f8e8
    style WN fill:#f3e8ff
```

---

## 7. 모듈 구성 및 디렉토리 구조

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart LR
    subgraph SCHED["⏰ main.py\nAPScheduler"]
        SC1["매시간\n수집 + 예측"]
        SC2["매일 자정\n재학습"]
    end

    subgraph COLLECT["수집"]
        C1["api_collector.py\n공공데이터 10시간 예측"]
        C2["sensor_reader.py\n현장 센서 실측값"]
    end

    subgraph PIPELINE["예측 파이프라인"]
        P1["feature_builder.py\n입력 시퀀스 구성"]
        P2["scaler.py\nMinMaxScaler 로드/적용"]
        P3["lstm_model.py\n모델 로드 및 예측"]
        P4["predict_pipeline.py\n전체 흐름 조율"]
    end

    subgraph TRAIN["학습"]
        T1["train_lstm.py\n슬라이딩 윈도우 + 학습"]
        T2["retrainer.py\n자동 재학습 스케줄"]
    end

    subgraph MON["모니터링"]
        M1["evaluator.py\nMAPE/RMSE"]
        M2["notifier.py\n이메일 알람"]
    end

    subgraph STORE["저장소"]
        DB["db_handler.py\nMySQL"]
        MDL["models/\nmodel.keras\nscaler.pkl"]
    end

    SC1 --> C1 & C2
    C1 & C2 -.-> DB
    DB --> P1 --> P2 --> P3 --> P4
    P4 -.-> DB
    SC2 --> T2 --> T1
    T1 -.-> MDL
    DB --> M1 --> M2
```

---

## 8. 디렉토리 구조

```
solar_lstm/
├── main.py                    # APScheduler 진입점
├── config.py                  # DB, API, 시스템 파라미터
│
├── collector/
│   ├── api_collector.py       # 공공데이터 10시간 예측 수집
│   └── sensor_reader.py       # 현장 센서 실측값 수신
│
├── db/
│   └── db_handler.py          # MySQL CRUD
│
├── pipeline/
│   ├── feature_builder.py     # 입력 시퀀스 구성 (34×8)
│   ├── scaler.py              # MinMaxScaler 로드/저장
│   ├── lstm_model.py          # LSTM 모델 정의 및 추론
│   └── predict_pipeline.py    # 매시간 예측 파이프라인
│
├── training/
│   ├── train_lstm.py          # 슬라이딩 윈도우 + 모델 학습
│   └── retrainer.py           # 자동 재학습 스케줄러
│
├── monitoring/
│   ├── evaluator.py           # MAPE, RMSE 계산
│   └── notifier.py            # 이메일 알람 (smtplib)
│
├── api/
│   └── api_server.py          # FastAPI 예측 결과 제공
│
└── models/
    ├── model.keras             # 현재 LSTM 모델
    ├── scaler.pkl              # MinMaxScaler (학습 시 fit)
    └── model_history/          # 이전 모델 백업
```

---

## 9. 주요 라이브러리

| 모듈 | 라이브러리 | 용도 |
|------|-----------|------|
| lstm_model.py | `tensorflow`, `keras` | LSTM 모델 정의·추론 |
| train_lstm.py | `tensorflow`, `keras`, `numpy` | 모델 학습 |
| feature_builder.py | `pandas`, `numpy` | 시퀀스 구성·시간 인코딩 |
| scaler.py | `sklearn.preprocessing` | MinMaxScaler |
| api_collector.py | `requests` | 공공데이터 API 호출 |
| sensor_reader.py | `paho-mqtt` | MQTT 센서 수신 |
| db_handler.py | `pymysql`, `sqlalchemy` | MySQL 연동 |
| evaluator.py | `sklearn.metrics`, `numpy` | 오차 평가 |
| notifier.py | `smtplib`, `email` | 이메일 알람 |
| main.py | `apscheduler` | 스케줄 자동화 |
| api_server.py | `fastapi`, `uvicorn` | REST API 서비스 |
