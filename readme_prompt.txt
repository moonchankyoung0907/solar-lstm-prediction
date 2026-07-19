이 프로젝트의 README.md를 작성해줘.

[목적]
이 README만 보고 따라하면 누구든 동일한 결과(Validation MAPE 19.50%)를 100% 재현할 수 있도록 자세하고 정확하게 작성. 외부 회사(세자에너지) 제출용이라 검증된 명령어와 함수명만 사용. 추측 금지, 실제 코드 기반으로만.

[작성 방식]
- 먼저 다음 파일들을 모두 읽어봐:
  - solar_lstm_xlsx/ 폴더의 모든 .py 파일 (config.py, data_loader.py, feature_builder.py, preprocessor.py, scaler.py, lstm_model.py, train.py, predict.py)
  - flask_app/app.py 및 flask_app/templates/ 안의 HTML
  - fetch_solar_data.py (루트에 있으면)
  - pyproject.toml
  - main.py
- 실제 함수명·변수명·실행 옵션·import 구문·하이퍼파라미터가 100% 일치하도록 작성
- 한국어, 마크다운 형식
- 기존 README.md 있으면 덮어써

[블록도 이미지 삽입]
README 안에 다음 블록도 이미지 4개를 마크다운 ![설명](docs/images/파일명) 형식으로 삽입할 자리 명시:
- docs/images/세자에너지_블록도.png → "1. 프로젝트 개요" 섹션
- docs/images/블록도_1_데이터수집.png → "4. 데이터 수집 파이프라인" 섹션
- docs/images/블록도_3_LSTM학습.png → "5. LSTM 모델 학습" 섹션
- docs/images/블록도_2_onsite측정.png → "9. 향후 확장 - 군산 현장 연동" 섹션

docs/images/ 폴더를 만들어줘. 이미지 파일은 내가 직접 넣을 거니까 폴더 구조랑 README에 참조 경로만 잡아줘.

[포함해야 할 섹션]
1. 프로젝트 개요 (세자에너지 사천 발전소, 향후 10시간 예측, MAPE 19.50%)
2. 환경 설정 (Python 3.11, pyproject.toml 의존성, GitHub clone)
3. 전체 시스템 흐름
4. 데이터 수집 파이프라인 (fetch_solar_data.py, Windows 작업 스케줄러, log.xlsx 컬럼)
5. LSTM 모델 학습 - 가장 자세히
   - train_log.xlsx 30일치 720시간
   - 입력 (35, 8) 구조 상세
   - 35 타임스텝: 과거 24h + 현재 1 + 미래 10h
   - 8 feature: 발전량/일사량/온도/예보일사량/예보온도/hour_sin/hour_cos/month_norm
   - 모델 구조: 2-layer LSTM (128→64) + Dropout + Dense (32→16→10), 파라미터 122,330
   - 64 epoch (Early Stopping), Validation MAPE 19.50%
6. 예측 실행 (predict.py, 기준 시각 2026-03-14 13:00 출력 예시)
7. Flask 웹 대시보드 (flask_app/app.py, 127.0.0.1:5000, MAPE 색상 코딩)
8. LSTM 알고리즘 동작 원리 (Forget/Input/Output Gate 상세 설명)
9. 향후 확장 - 군산 현장 연동 (WH-2300S, SylCin BMS, 인버터, RS485)
10. 디렉토리 구조
11. 트러블슈팅 (Python 3.12 호환, TensorFlow GPU, 작업 폴더)
12. 작성자 정보:
    - 군산대학교 임베디드 소프트웨어학과 2101050 문찬경
    - GitHub: github.com/moonchankyoung0907/solar-lstm-prediction
    - YouTube 시연 영상: https://youtu.be/F4SNUVw4xxo
    - 이메일: mck0801@naver.com

지금 시작해. 코드 다 읽고 자세하게 README.md를 프로젝트 루트에 만들고, docs/images/ 폴더도 같이 만들어줘.