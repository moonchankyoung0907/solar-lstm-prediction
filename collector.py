import os
import time
from datetime import datetime

import openpyxl

TXT_PATH = r"C:\Users\sejae\Desktop\웨더게이트 소프트웨어\WH-2300S PC소프트웨어 25.03 (유저용)\WH-2300S 관련 User 제공자료\WH-2300S display software\WH24Data.txt"
XLSX_PATH = r"C:\Users\sejae\Desktop\sensor_log.xlsx"

# 2026-09-17: WH24Collector(수동 트리거)와 WH24AutoPush(30분 정기) 작업이 둘 다 이
# collector.py를 그대로 실행하는데, 두 실행이 거의 동시에 겹치면서 같은 sensor_log.xlsx를
# openpyxl로 동시에 열고-저장(wb.save)하다가 파일이 실제로 손상(zip CRC 오류)된 사고가 있었다.
# 두 작업 모두 이 스크립트 하나를 그대로 거치므로, 여기 파일 락 하나만 걸면 두 작업 다 보호된다.
LOCK_PATH = XLSX_PATH + ".lock"
LOCK_STALE_SECONDS = 300  # 5분 - 비정상 종료(강제 킬 등)로 못 지워진 락은 이 시간 지나면 무시하고 강탈
LOCK_WAIT_SECONDS = 60    # 락 대기 최대 시간 - 이 안에 못 얻으면 이번 실행은 스킵(다음 주기에 다시 시도)
LOCK_POLL_INTERVAL = 2


def _read_lock_holder():
    """락을 잡고 있는 쪽이 누구인지(pid/시작시각) 로그용으로 읽어온다 - 실패해도 조용히 넘어간다."""
    try:
        # utf-8-sig: 누군가 메모장 등으로 락 파일을 열어봤다가 BOM이 붙은 채로 저장되는
        # 경우까지 방어(일반 "utf-8"은 BOM을 안 벗겨내 print()에서 cp949 콘솔이면 깨짐).
        with open(LOCK_PATH, encoding="utf-8-sig") as f:
            return f.read().strip()
    except OSError:
        return "확인불가"


def _acquire_lock():
    """sensor_log.xlsx.lock을 원자적으로 생성해서 락을 잡는다(O_CREAT|O_EXCL - 이미 있으면
    FileExistsError로 실패, 두 프로세스가 동시에 시도해도 운영체제 레벨에서 하나만 성공).
    이미 락이 있으면: 5분 넘은 stale lock이면 강제로 지우고 재획득 시도, 아니면 최대
    LOCK_WAIT_SECONDS 동안 폴링하며 대기 - 그래도 못 얻으면 스킵(False 반환, 이번 실행은
    건너뛰고 다음 주기에 다시 시도). 어떤 경우든 무슨 일이 있었는지 표준출력에 남긴다
    (두 작업 모두 .bat 래퍼가 stdout을 로그 파일로 리다이렉트하는 기존 구조를 그대로 이용)."""
    deadline = time.time() + LOCK_WAIT_SECONDS
    while True:
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"pid={os.getpid()} started={datetime.now().isoformat(timespec='seconds')}\n")
            print(f"[lock] 락 획득 성공 (pid={os.getpid()})")
            return True
        except FileExistsError:
            try:
                age = time.time() - os.path.getmtime(LOCK_PATH)
            except OSError:
                age = 0  # 확인하는 사이 다른 프로세스가 이미 지웠으면 바로 재시도
            if age > LOCK_STALE_SECONDS:
                holder = _read_lock_holder()
                print(f"[lock] stale lock 감지(age={age:.0f}s > {LOCK_STALE_SECONDS}s, 이전 보유자: {holder})"
                      f" - 강제 해제 후 재획득 시도 (pid={os.getpid()})")
                try:
                    os.remove(LOCK_PATH)
                except OSError:
                    pass
                continue
            if time.time() >= deadline:
                holder = _read_lock_holder()
                print(f"[lock] 락 획득 실패 - {LOCK_WAIT_SECONDS}초 대기했지만 여전히 사용 중"
                      f"(보유자: {holder}) - 이번 실행(pid={os.getpid()})은 스킵합니다")
                return False
            print(f"[lock] sensor_log.xlsx 사용 중(보유자: {_read_lock_holder()}, age={age:.0f}s)"
                  f" - {LOCK_POLL_INTERVAL}초 후 재시도 (pid={os.getpid()} 대기)")
            time.sleep(LOCK_POLL_INTERVAL)


def _release_lock():
    try:
        os.remove(LOCK_PATH)
        print(f"[lock] 락 해제 완료 (pid={os.getpid()})")
    except OSError:
        pass

# rain(raw)은 강수 센서의 누적 tip 카운터. WH24가 Fine Offset 7-in-1 계열이고
# 동계열 모델의 공식 강수 스텝이 0.3mm/tip으로 확인되어(2026-08-18), raw*RAIN_MM_PER_TICK = mm(누적).
RAIN_MM_PER_TICK = 0.3

def parse_line(line):
    try:
        parts = line.strip().split(",")
        if len(parts) < 10:
            return None
        dt = parts[0].strip()
        # "▲"는 cp949 디코딩 과정에서 "°"가 깨진 것 (온도의 "▲C"와 동일한 현상). 풍향은 0~360도.
        wind_dir = parts[1].strip().replace("▲", "").strip()
        temp = parts[2].strip().replace("▲C","").replace("℃","").strip()
        humidity = parts[3].strip().replace("%","").strip()
        wind = parts[4].strip().replace("m/s","").strip()
        rain = parts[6].strip()
        uv = parts[7].strip()      # 자외선 원시값 (WH24 UART Display 화면의 "UV")
        uvi = parts[8].strip()     # 자외선 지수 0~11 (WH24 UART Display 화면의 "UVI")
        lux = parts[9].strip().replace("lux","").strip()
        # CRC 에러 체크
        crc = "OK"
        for part in parts:
            if "CRC" in part or "ERROR" in part:
                crc = "ERROR"
                break
        rain_val = float(rain)
        rain_mm = round(rain_val * RAIN_MM_PER_TICK, 1)
        return [dt, float(temp), float(humidity), float(wind), rain_val, float(lux), crc, float(wind_dir), float(uv), float(uvi), rain_mm]
    except:
        return None

def apply_interpolation(ws):
    max_row = ws.max_row
    data_cols = [2, 3, 4, 5, 6, 8, 9, 10, 11]  # temperature, humidity, wind_speed, rainfall, light_lux, wind_direction, uv, uvi, rainfall_mm (7=crc_status 제외)
    for row_idx in range(2, max_row + 1):
        crc = ws.cell(row=row_idx, column=7).value
        if crc == "ERROR":
            for col in data_cols:
                prev_val = None
                next_val = None
                if row_idx > 2:
                    prev_val = ws.cell(row=row_idx-1, column=col).value
                if row_idx < max_row:
                    next_val = ws.cell(row=row_idx+1, column=col).value
                if prev_val is not None and next_val is not None:
                    ws.cell(row=row_idx, column=col).value = (prev_val + next_val) / 2
                elif prev_val is not None:
                    ws.cell(row=row_idx, column=col).value = prev_val
                elif next_val is not None:
                    ws.cell(row=row_idx, column=col).value = next_val

def main():
    if not _acquire_lock():
        return  # 다른 실행이 아직 sensor_log.xlsx를 쓰는 중 - 이번 주기는 건너뛴다
    try:
        if os.path.exists(XLSX_PATH):
            wb = openpyxl.load_workbook(XLSX_PATH)
            ws = wb.active
            header = [c.value for c in ws[1]]
            # 7번째 컬럼(crc_status) 라벨이 예전부터 비어있는 파일이 있어 데이터는 정상이어도
            # 헤더만 None인 경우가 있음 - 라벨만 보정
            if len(header) >= 7 and not header[6]:
                ws.cell(row=1, column=7, value="crc_status")
                header[6] = "crc_status"
            for col_name in ("wind_direction", "uv", "uvi", "rainfall_mm"):
                if col_name not in header:
                    ws.cell(row=1, column=len(header) + 1, value=col_name)
                    header.append(col_name)
        else:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(["datetime","temperature","humidity","wind_speed","rainfall","light_lux","crc_status","wind_direction","uv","uvi","rainfall_mm"])

        existing = set()
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0]:
                existing.add(str(row[0]))

        new_count = 0
        with open(TXT_PATH, "r", encoding="cp949", errors="ignore") as f:
            for line in f:
                if line.strip() == "":
                    continue
                row = parse_line(line)
                if row and str(row[0]) not in existing:
                    ws.append(row)
                    existing.add(str(row[0]))
                    new_count += 1

        apply_interpolation(ws)
        wb.save(XLSX_PATH)
        print(f"완료! 새로 추가된 데이터: {new_count}개")
    finally:
        _release_lock()

if __name__ == "__main__":
    main()