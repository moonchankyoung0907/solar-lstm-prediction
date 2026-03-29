# LSTM 기반 태양광발전소 10시간 발전량 예측 시스템 (시뮬레이션 버전)

> 📌 **공공데이터 API 및 현장 센서는 Python 시뮬레이터로 대체**
> `simulator.py` 하나만 실제 연동 코드로 교체하면 실 운용 전환 가능

---

## 1. 전체 시스템 블록도

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart TD
    subgraph SIM["🎲 simulator.py (Python 시뮬레이터)"]
        S1["forecast_simulator()\n공공데이터 대체\n일사량·기온 10시간 예측값 생성\nirr_fore(t+1~t+10), temp_fore(t+1~t+10)"]
        S2["sensor_simulator()\n현장 센서 대체\n현재 일사량·기온 실측값 생성\nirr_now, temp_now"]
        S3["inverter_simulator()\n인버터 대체\n현재 실제 발전량 생성\npower_now (kW)"]
    end

    subgraph DB["🗄️ MySQL (db_handler.py)"]
        DB1["sensor_data\nirr, temp, power 실측 이력"]
        DB2["forecast_data\nirr_fore, temp_fore 예측 이력"]
        DB3["prediction_result\nt+1~t+10 예측 발전량"]
        DB4["error_log\nMAPE, RMSE 오차 기록"]
        DB5["model_log\n재학습 이력"]
    end

    subgraph FEATURE["🔧 feature_builder.py\n입력 시퀀스 구성"]
        F1["현재 실측값 (t=0)\nirr_now, temp_now, power_now"]
        F2["10시간 예측값 (t+1~t+10)\nirr_fore, temp_fore"]
        F3["시간 특성\nhour_sin, hour_cos, month_norm"]
        F4["과거 24시간 실측 이력\n(DB에서 로드)\nshape: 24 × 3"]
    end

    subgraph LSTM_BLOCK["🧠 lstm_model.py\nLSTM 예측 모델"]
        L1["입력 텐서\nshape: (1, 34, 8)"]
        L2["LSTM Layer 1\nunits=128, return_seq=True"]
        L3["Dropout 0.2"]
        L4["LSTM Layer 2\nunits=64, return_seq=False"]
        L5["Dropout 0.2"]
        L6["Dense(32, relu)"]
        L7["Dense(10, linear)\n→ t+1~t+10 발전량"]
    end

    subgraph OUTPUT["📤 예측 결과"]
        O1["역정규화\nscaler.inverse_transform()"]
        O2["10시간 발전량 예측\nt+1~t+10 (kW)"]
    end

    subgraph MONITOR["📊 모니터링"]
        E1["evaluator.py\nMAPE · RMSE 계산"]
        E2["retrainer.py\n매일 자정 자동 재학습"]
        E3["notifier.py\n오차 초과 이메일 알람"]
        E4["api_server.py\nFastAPI 결과 조회"]
    end

    %% 시뮬레이터 → DB 저장 (점선)
    S1 -.-> DB2
    S2 & S3 -.-> DB1

    %% 주 데이터 흐름: DB → FEATURE → LSTM → OUTPUT
    DB1 -->|"과거 24시간 이력"| F4
    DB1 -->|"현재 실측"| F1
    DB2 -->|"10시간 예측"| F2
    F1 & F2 & F3 & F4 --> L1
    L1 --> L2 --> L3 --> L4 --> L5 --> L6 --> L7
    L7 --> O1 --> O2

    %% 결과 저장 및 모니터링
    O2 -.-> DB3
    DB3 --> E1
    DB1 -->|"실측 발전량"| E1
    E1 -->|"오차 누적"| E2
    E1 -->|"임계 초과"| E3
    DB3 --> E4

    style SIM fill:#fff3cd,stroke:#ffc107
    style LSTM_BLOCK fill:#f3e8ff,stroke:#6f42c1
    style OUTPUT fill:#d4edda,stroke:#198754
```

---

## 2. 시뮬레이터 상세 설계 (simulator.py)

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart TD
    INIT["simulator.py 초기화\n· 시스템 용량 (kW)\n· 위도 경도\n· 계절 기준 기온\n· 노이즈 레벨"]

    INIT --> TIME["datetime.now()\n현재 시각 확인"]

    TIME --> SOLAR["태양 고도 계산\nhour_angle 기반\n일출 06:00 / 일몰 19:00 가정"]

    SOLAR --> F["forecast_simulator()\n미래 10시간 예측값 생성"]
    SOLAR --> SE["sensor_simulator()\n현재 실측값 생성"]
    SOLAR --> INV["inverter_simulator()\n현재 발전량 생성"]

    subgraph FORECAST["forecast_simulator() 내부"]
        FI["기준 일사량 곡선 계산\n정오 피크 가우시안 분포\nt+1 ~ t+10 각 시간대"]
        FII["랜덤 노이즈 추가\nnp.random.normal(0, 50)\n구름·날씨 변동 모사"]
        FIII["물리 범위 클리핑\n일사량: clip(0, 1000) W/m²\n기온: clip(-10, 45) ℃"]
        FI --> FII --> FIII
    end

    subgraph SENSOR_SIM["sensor_simulator() 내부"]
        SI["현재 시각 기준\n기준 일사량 계산"]
        SII["노이즈 ±5% 추가\nnp.random.uniform(-0.05, 0.05)"]
        SIII["모듈 온도 추정\nNOCT 공식 적용\nT_mod = T_air + (NOCT-20)/800 × irr"]
        SI --> SII --> SIII
    end

    subgraph INVERTER_SIM["inverter_simulator() 내부"]
        II["물리 공식으로\n기준 발전량 계산\nP = cap × (irr/1000) × η × PR"]
        III["인버터 효율 노이즈\nnp.random.uniform(-0.03, 0.03)"]
        IIII["야간 처리\nirr == 0 → power = 0"]
        II --> III --> IIII
    end

    F --> FI
    SE --> SI
    INV --> II

    style FORECAST fill:#e8f4f8
    style SENSOR_SIM fill:#e8f8e8
    style INVERTER_SIM fill:#f8f0e8
```

---

## 3. 시뮬레이터 데이터 생성 규칙

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart LR
    subgraph TIME_RULE["⏰ 시간대별 생성 규칙"]
        T1["야간\n21:00 ~ 05:00\n일사량 = 0 W/m²\n발전량 = 0 kW"]
        T2["오전\n06:00 ~ 11:00\n일사량 점진 증가\n0 → 800 W/m²"]
        T3["정오\n12:00 ~ 13:00\n최대 일사량\n700 ~ 1000 W/m²"]
        T4["오후\n14:00 ~ 19:00\n일사량 점진 감소\n800 → 0 W/m²"]
    end

    subgraph NOISE["🎲 노이즈 규칙"]
        N1["일사량 노이즈\nnormal(0, 50) W/m²\n구름 변동 모사"]
        N2["기온 노이즈\nnormal(0, 2) ℃\n계절별 기준값 기반"]
        N3["발전량 노이즈\nuniform(-3%, +3%)\n인버터 효율 변동"]
    end

    subgraph SEASON["📅 계절별 기준 기온"]
        SS1["봄 3~5월\n15 ℃"]
        SS2["여름 6~8월\n30 ℃"]
        SS3["가을 9~11월\n18 ℃"]
        SS4["겨울 12~2월\n2 ℃"]
    end
```

---

## 4. LSTM 입력 시퀀스 구성

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart LR
    subgraph PAST["과거 24시간 실측\n(DB 조회: t-24 ~ t-1)"]
        P1["각 스텝 3개 feature\nirr_actual\ntemp_actual\npower_actual\n→ shape: (24, 3)"]
    end

    subgraph CURR["현재 실측 (t=0)\n(sensor_simulator 생성)"]
        C1["irr_now\ntemp_now\npower_now\n→ shape: (1, 3)"]
    end

    subgraph FORE["미래 10시간 예측\n(forecast_simulator 생성)"]
        F1["각 스텝 2개 feature\nirr_forecast\ntemp_forecast\n→ shape: (10, 2)"]
    end

    subgraph TIME_ENC["시간 인코딩\n(feature_builder 생성)"]
        TE1["hour_sin = sin(2π×hour/24)\nhour_cos = cos(2π×hour/24)\nmonth_norm = month/12\n→ shape: (34, 3)"]
    end

    TEN["통합 입력 텐서\n(Zero-padding 후 결합)\nshape: (1, 34, 8)\n\n8 features:\n① irr_actual\n② temp_actual\n③ power_actual\n④ irr_forecast\n⑤ temp_forecast\n⑥ hour_sin\n⑦ hour_cos\n⑧ month_norm"]

    O1["LSTM 출력\nshape: (1, 10)\nt+1 ~ t+10\n발전량 예측 (정규화)"]

    P1 & C1 & F1 & TE1 --> TEN --> O1

    style TEN fill:#f3e8ff
    style O1 fill:#d4edda
```

---

## 5. LSTM 모델 아키텍처

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart TD
    IN["입력층\nInput shape: (34, 8)"]

    subgraph B1["LSTM Block 1"]
        L1["LSTM(128, return_sequences=True)"]
        D1["Dropout(0.2)"]
    end

    subgraph B2["LSTM Block 2"]
        L2["LSTM(64, return_sequences=False)"]
        D2["Dropout(0.2)"]
    end

    subgraph B3["Dense Block"]
        FC1["Dense(32, activation='relu')"]
        FC2["Dense(16, activation='relu')"]
    end

    OUT["출력층\nDense(10, activation='linear')\n→ t+1 ~ t+10 발전량"]

    COMPILE["컴파일\noptimizer = Adam(lr=0.001)\nloss = MSE\nmetrics = MAE"]

    CB["콜백\nEarlyStopping(patience=10)\nModelCheckpoint(best only)\nReduceLROnPlateau"]

    IN --> L1 --> D1 --> L2 --> D2 --> FC1 --> FC2 --> OUT
    OUT --> COMPILE & CB

    style IN fill:#e8f4f8
    style OUT fill:#d4edda
    style COMPILE fill:#fff3cd
```

---

## 6. 예측 실행 파이프라인 (predict_pipeline.py)

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart TD
    START["🟢 predict_pipeline.py\n(매시간 APScheduler 호출)"]

    GEN["simulator.py 호출\n① forecast_simulator() → DB 저장\n② sensor_simulator() → DB 저장\n③ inverter_simulator() → DB 저장"]

    LOAD["db_handler.py\nget_latest_data()\n과거 24h 이력 + 현재 + 예측값 로드"]

    PRE["preprocessor.py\n이상치 제거 IQR\n결측값 선형 보간\n야간 데이터 마스킹"]

    QCHECK{"데이터 품질 검사\n필수 컬럼 존재?\n값 범위 정상?"}

    QALERT["notifier.py\n데이터 이상 알람 발송"]
    STOP["⛔ 예측 중단\n오류 로그 기록"]

    FE["feature_builder.py\n입력 시퀀스 구성\nshape: (1, 34, 8)"]

    SCALE["scaler.py\nMinMaxScaler 로드 (scaler.pkl)\n입력 정규화"]

    PREDICT["lstm_model.py\nmodel.keras 로드\nmodel.predict(X)\n→ shape: (1, 10)"]

    INVERSE["scaler.py\ninverse_transform()\n역정규화 → kW 단위"]

    CONF["신뢰구간 계산\nlower = pred × 0.90\nupper = pred × 1.10"]

    SAVE["db_handler.py\ninsert_prediction()\nt+1~t+10 결과 저장"]

    EVAL["evaluator.py\n이전 예측 vs 실측 비교\nMAPE, RMSE 계산 후 DB 저장"]

    MCHECK{"MAPE > 10%?"}
    NOTIFY["notifier.py\n오차 초과 이메일 발송"]
    END["✅ 완료"]

    START --> GEN --> LOAD --> PRE --> QCHECK
    QCHECK -->|"불량"| QALERT --> STOP
    QCHECK -->|"정상"| FE --> SCALE --> PREDICT --> INVERSE --> CONF --> SAVE --> EVAL --> MCHECK
    MCHECK -->|"Yes"| NOTIFY --> END
    MCHECK -->|"No"| END

    style GEN fill:#fff3cd,stroke:#ffc107
    style QCHECK fill:#fff3cd
    style MCHECK fill:#fff3cd
    style QALERT fill:#f8d7da
    style STOP fill:#f8d7da
    style NOTIFY fill:#f8d7da
    style END fill:#d4edda
```

---

## 7. 학습 파이프라인 (train_lstm.py)

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart TD
    START["train_lstm.py 실행\n(초기 실행 or 매일 자정 재학습)"]

    LOAD["DB에서 학습 데이터 로드\n과거 90일 시뮬 데이터\n(sensor_data + forecast_data)"]

    CLEAN["전처리\n· 야간 제외 (일조시간만)\n· IQR 이상치 제거\n· 결측값 보간"]

    WINDOW["슬라이딩 윈도우 생성\nwindow_size = 34 (24 past + 1 now + 10 fore)\nstep = 1\n→ 다수의 (X, y) 샘플"]

    SCALE["MinMaxScaler fit\n학습 데이터 기준으로 fit\nscaler.pkl 저장"]

    SPLIT["시계열 분할\nTrain 80% / Val 20%\nshuffle = False (시간 순서 유지)"]

    BUILD["LSTM 모델 빌드\nKeras Sequential\nLSTM×2 + Dense×2"]

    TRAIN["모델 학습\nepochs = 100\nbatch_size = 32\nEarlyStopping(patience=10)\nModelCheckpoint 저장"]

    EVAL_M{"검증 MAPE\n신모델 < 구모델?"}

    REPLACE["model.keras 교체\nscaler.pkl 교체\nmodel_history/ 백업"]

    KEEP["기존 모델 유지\n로그만 기록"]

    LOG["model_log 테이블\n재학습 결과 DB 저장"]

    START --> LOAD --> CLEAN --> WINDOW --> SCALE --> SPLIT --> BUILD --> TRAIN --> EVAL_M
    EVAL_M -->|"Yes"| REPLACE
    EVAL_M -->|"No"| KEEP
    REPLACE & KEEP --> LOG

    style EVAL_M fill:#fff3cd
    style REPLACE fill:#d4edda
    style KEEP fill:#e2e3e5
```

---

## 8. 전체 자동화 스케줄 (main.py)

```mermaid
%%{ init: { 'flowchart': { 'curve': 'linear' } } }%%
flowchart LR
    subgraph SCHED["⏰ APScheduler (main.py)"]
        SC1["매시간 정각\ncron: hour='*'"]
        SC2["매일 자정\ncron: hour=0, minute=0"]
    end

    subgraph HOURLY["매시간 작업"]
        H1["simulator.py\n① forecast_simulator()\n② sensor_simulator()\n③ inverter_simulator()"]
        H2["predict_pipeline.py\n예측 실행 (t+1~t+10)"]
        H3["evaluator.py\n이전 예측 오차 계산"]
    end

    subgraph DAILY["매일 자정 작업"]
        D1["retrainer.py\n90일 데이터로\nLSTM 재학습"]
        D2["model 교체 판단\nMAPE 비교"]
    end

    subgraph API["🚀 api_server.py\nFastAPI (항시 실행)"]
        AP1["GET /predict\n최신 10시간 예측 조회"]
        AP2["GET /metrics\nMAPE, RMSE 조회"]
        AP3["GET /simulate\n시뮬 데이터 조회"]
    end

    SC1 --> H1 --> H2 --> H3
    SC2 --> D1 --> D2
    H2 -.->|"결과 저장"| API
    D2 -.->|"모델 갱신"| API
```

---

## 9. 데이터베이스 스키마 (ERD)

```mermaid
erDiagram
    SENSOR_DATA {
        int id PK
        datetime timestamp
        float irradiance "일사량 W/m² (시뮬)"
        float temp_module "모듈 온도 ℃ (시뮬)"
        float temp_air "외기 온도 ℃ (시뮬)"
        float power_actual "실측 발전량 kW (시뮬)"
        boolean is_simulated "시뮬 여부 플래그"
    }

    FORECAST_DATA {
        int id PK
        datetime created_at "생성 시각"
        datetime forecast_time "예측 대상 시각"
        float irradiance_forecast "예측 일사량 (시뮬)"
        float temp_forecast "예측 기온 (시뮬)"
        int horizon "예측 시간 1~10"
        boolean is_simulated "시뮬 여부 플래그"
    }

    PREDICTION_RESULT {
        int id PK
        datetime created_at
        datetime target_time "예측 대상 시각"
        float power_lstm "LSTM 예측 kW"
        float confidence_lower "신뢰 하한"
        float confidence_upper "신뢰 상한"
    }

    ERROR_LOG {
        int id PK
        datetime timestamp
        float power_predicted
        float power_actual
        float mape
        float rmse
    }

    MODEL_LOG {
        int id PK
        datetime trained_at
        float mape_new
        float mape_old
        boolean adopted "모델 교체 여부"
        string model_path
    }

    SENSOR_DATA ||--o{ ERROR_LOG : "실측값 비교"
    FORECAST_DATA ||--o{ PREDICTION_RESULT : "예측 생성"
    PREDICTION_RESULT ||--o{ ERROR_LOG : "오차 기록"
    ERROR_LOG ||--o{ MODEL_LOG : "재학습 트리거"
```

---

## 10. 프로젝트 디렉토리 구조

```
solar_lstm_sim/
├── main.py                    # APScheduler 진입점
├── config.py                  # DB, 시스템 용량, LSTM 하이퍼파라미터
│
├── simulator/
│   └── simulator.py           # ⭐ 랜덤 시뮬레이터
│                              #    (추후 API + MQTT로 교체)
│
├── db/
│   └── db_handler.py          # MySQL CRUD (pymysql)
│
├── pipeline/
│   ├── preprocessor.py        # 이상치 제거, 보간
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
    ├── scaler.pkl              # MinMaxScaler
    └── model_history/          # 이전 모델 백업
```

> ⭐ `simulator/simulator.py` 하나만 아래 두 파일로 교체하면 실 운용 전환 완료
> - `collector/api_collector.py` → 공공데이터 API 호출
> - `collector/sensor_reader.py` → MQTT 현장 센서 수신

---

## 11. 주요 라이브러리

| 모듈 | 라이브러리 | 용도 |
|------|-----------|------|
| simulator.py | `numpy`, `datetime` | 랜덤 시뮬 데이터 생성 |
| db_handler.py | `pymysql`, `sqlalchemy` | MySQL 연동 |
| preprocessor.py | `pandas`, `numpy`, `scipy` | 전처리 |
| feature_builder.py | `pandas`, `numpy` | 시퀀스 구성·시간 인코딩 |
| scaler.py | `sklearn.preprocessing` | MinMaxScaler |
| lstm_model.py | `tensorflow`, `keras` | LSTM 모델 정의·추론 |
| train_lstm.py | `tensorflow`, `keras`, `numpy` | 모델 학습 |
| retrainer.py | `apscheduler` | 자동 재학습 스케줄 |
| evaluator.py | `sklearn.metrics`, `numpy` | 오차 평가 |
| notifier.py | `smtplib`, `email` | 이메일 알람 |
| api_server.py | `fastapi`, `uvicorn` | REST API 서비스 |
| main.py | `apscheduler` | 전체 스케줄 자동화 |
