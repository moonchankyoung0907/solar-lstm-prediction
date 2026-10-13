@echo off
setlocal
cd C:\Users\sejae\Desktop
set "LOGDIR=C:\Users\sejae\Desktop\tmp"
set "LOG=%LOGDIR%\inverter_auto_push.log"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

rem keep only the last 5000 lines of the log
if exist "%LOG%" powershell -NoProfile -ExecutionPolicy Bypass -Command "$l = Get-Content -LiteralPath '%LOG%' -Tail 5000; Set-Content -LiteralPath '%LOG%' -Value $l"

>> "%LOG%" echo [%date% %time%] START inverter_auto_push
git add inverter_log.xlsx >> "%LOG%" 2>&1
git commit -m "auto: inverter data update" >> "%LOG%" 2>&1
git fetch origin main >> "%LOG%" 2>&1
git merge origin/main --no-edit >> "%LOG%" 2>&1
git push origin master:main >> "%LOG%" 2>&1
set "PRC=%errorlevel%"
>> "%LOG%" echo [%date% %time%] END git push exit code %PRC%
exit /b %PRC%
