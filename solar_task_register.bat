@echo off
REM 일사량 센서 5분 주기 수집 작업 등록 - COM 포트를 solar_reader.py에 채운 뒤 1회만 실행할 것.
REM (포트가 비어 있는 상태로 등록하면 5분마다 PORT_NOT_SET 행만 쌓인다)
REM 기존 InverterCollector(5분)와 같은 방식이며, git push는 WH24AutoPush(30분)가 함께 처리한다.

schtasks /Create /TN SolarCollector /SC MINUTE /MO 5 /F /TR "C:\Users\sejae\AppData\Local\Programs\Python\Python311\python.exe C:\Users\sejae\Desktop\solar_collector.py"

echo.
echo --- 등록 결과 ---
schtasks /Query /TN SolarCollector
pause
