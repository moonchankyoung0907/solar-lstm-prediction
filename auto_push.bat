@echo off
setlocal
cd /d C:\Users\sejae\Desktop
set "PY=C:\Users\sejae\AppData\Local\Programs\Python\Python311\python.exe"
set "LOGDIR=C:\Users\sejae\Desktop\tmp"
set "LOG=%LOGDIR%\auto_push.log"
rem stdout is redirected to a file -> avoid UnicodeEncodeError on print()
set "PYTHONIOENCODING=cp949:replace"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

rem keep only the last 5000 lines of the log
if exist "%LOG%" powershell -NoProfile -ExecutionPolicy Bypass -Command "$l = Get-Content -LiteralPath '%LOG%' -Tail 5000; Set-Content -LiteralPath '%LOG%' -Value $l"

>> "%LOG%" echo [%date% %time%] START auto_push

rem skip if collector.py is already running (WH24Collector task / manual run)
rem '\collector.py' does not match inverter_collector.py / solar_collector.py
wmic process where "name='python.exe' and commandline like '%%\\collector.py%%'" get processid 2>nul | findstr /r "[0-9]" >nul
if not errorlevel 1 (
    >> "%LOG%" echo [%date% %time%] SKIP collector.py already running
    exit /b 0
)

"%PY%" C:\Users\sejae\Desktop\collector.py >> "%LOG%" 2>&1
set "RC=%errorlevel%"
>> "%LOG%" echo [%date% %time%] collector exit code %RC%
if not "%RC%"=="0" (
    >> "%LOG%" echo [%date% %time%] FAIL collector exit code %RC% - git add/commit/push skipped
    exit /b 1
)

git add sensor_log.xlsx >> "%LOG%" 2>&1
if exist archive git add archive >> "%LOG%" 2>&1
if exist solar_log.xlsx git add solar_log.xlsx >> "%LOG%" 2>&1
git commit -m "auto: sensor data update" >> "%LOG%" 2>&1
git fetch origin main >> "%LOG%" 2>&1
git merge origin/main --no-edit >> "%LOG%" 2>&1
git push origin master:main >> "%LOG%" 2>&1
set "PRC=%errorlevel%"
>> "%LOG%" echo [%date% %time%] END git push exit code %PRC%
exit /b %PRC%
