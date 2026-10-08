import bisect
import csv
import os
import time
import zipfile
from datetime import datetime, timedelta

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


def _log(msg):
    """단계별 시각을 남긴다 - auto_push.log에서 UART Display 크래시 시각과 대조하기 위함(2026-10-08)."""
    now = datetime.now()
    print(f"[{now:%Y-%m-%d %H:%M:%S}.{now.microsecond // 1000:03d}] [collector] {msg}", flush=True)


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
            _log(f"[lock] 락 획득 성공 (pid={os.getpid()})")
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


# 2026-10-07: 10:47 실행에서 wb.save 도중 예외(메모리 부족 추정)가 나 sensor_log.xlsx가 시트 없이
# 2KB짜리로 덮어써지고 그대로 push된 사고가 있었다. 원본에 직접 저장하지 않고 같은 폴더의 임시 파일에
# 저장 -> zip 항목 검증 -> os.replace로 교체한다. 실패하면 원본은 그대로 두고 비정상 종료(exit 1).
TMP_PATH = XLSX_PATH + ".tmp"
REQUIRED_ENTRIES = ("[Content_Types].xml", "xl/worksheets/sheet1.xml")


def _safe_save(wb):
    try:
        _log("저장 시작")
        wb.save(TMP_PATH)
        with zipfile.ZipFile(TMP_PATH) as z:
            names = set(z.namelist())
        missing = [n for n in REQUIRED_ENTRIES if n not in names]
        if missing:
            raise RuntimeError(f"임시 파일 검증 실패 - 누락 항목: {missing}")
        os.replace(TMP_PATH, XLSX_PATH)
        _log("저장 완료")
    except BaseException as e:  # MemoryError 등 포함
        print(f"[save] 저장 실패({type(e).__name__}: {e}) - 원본은 그대로 두고 임시 파일 삭제 후 종료")
        try:
            os.remove(TMP_PATH)
        except OSError:
            pass
        raise SystemExit(1)


def _release_lock():
    try:
        os.remove(LOCK_PATH)
        print(f"[lock] 락 해제 완료 (pid={os.getpid()})")
    except OSError:
        pass

# rain(raw)은 강수 센서의 누적 tip 카운터. WH24가 Fine Offset 7-in-1 계열이고
# 동계열 모델의 공식 강수 스텝이 0.3mm/tip으로 확인되어(2026-08-18), raw*RAIN_MM_PER_TICK = mm(누적).
RAIN_MM_PER_TICK = 0.3

# 일사량 센서(vctec P000BDFU)는 solar_collector.py가 5분 주기로 별도 파일에 쌓는다.
# 여기서는 그 값을 타임스탬프로 맞춰 sensor_log.xlsx에 합치기만 한다.
# 파일이 없으면(=센서 미연결) 아래 로직은 전부 no-op이다.
SOLAR_XLSX_PATH = r"C:\Users\sejae\Desktop\solar_log.xlsx"
# 일사량 폴링 주기(5분)의 절반보다 크게 잡아 모든 행이 가장 가까운 표본을 갖도록 한다.
SOLAR_MATCH_TOLERANCE_SEC = 300

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

def _parse_dt(value):
    """엑셀 셀의 시각 값을 datetime으로. WH24 로그는 "2026-04-23 1:49:17"처럼
    시각이 0으로 패딩되지 않는 경우가 있는데 strptime의 %H가 이를 받아준다."""
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _load_solar_samples():
    """solar_log.xlsx에서 (시각, 일사량)을 시간순으로 읽는다.
    파일이 없거나(센서 미연결) 열리지 않으면 빈 리스트 -> 병합 전체가 no-op."""
    if not os.path.exists(SOLAR_XLSX_PATH):
        return []
    try:
        wb = openpyxl.load_workbook(SOLAR_XLSX_PATH, read_only=True, data_only=True)
    except Exception:
        # 5분 주기 작업이 저장 중이면 잠겨 있을 수 있다. 다음 실행 때 합치면 된다.
        return []

    samples = []
    try:
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or len(row) < 2 or row[0] is None or row[1] is None:
                continue
            ts = _parse_dt(row[0])
            if ts is None:
                continue
            try:
                samples.append((ts, float(row[1])))
            except (TypeError, ValueError):
                continue
    finally:
        wb.close()

    samples.sort(key=lambda item: item[0])
    return samples


def _nearest_value(times, samples, ts):
    """ts에 가장 가까운 표본값. 허용 오차를 벗어나면 None."""
    pos = bisect.bisect_left(times, ts)
    best = None
    for i in (pos - 1, pos):
        if 0 <= i < len(samples):
            gap = abs((samples[i][0] - ts).total_seconds())
            if gap <= SOLAR_MATCH_TOLERANCE_SEC and (best is None or gap < best[0]):
                best = (gap, samples[i][1])
    return best[1] if best else None


# 2026-10-08: WH24 UART Display가 이 스크립트 실행 1~2분 뒤(=WH24Data.txt 전체 읽기 구간 추정)에
# 0xc0000417로 반복 크래시. txt를 통째로 오래 열어두지 않도록, 파일 끝에서 필요한 만큼만 바이트로
# 한 번에 읽고 즉시 닫은 뒤 메모리에서 파싱한다. 필요한 구간까지 못 거슬러 가면 기존 전체 읽기로 폴백.
TAIL_LOOKBACK = timedelta(days=3)         # 기본: 최근 3일치는 항상 다시 훑는다(중복은 existing으로 걸러짐)
TAIL_MARGIN = timedelta(hours=1)          # sensor_log 마지막 행 시각 이전 여유
TAIL_INITIAL_BYTES = 4 * 1024 * 1024      # 16초 간격 약 160B/줄 기준 4~5일치
TAIL_MAX_BYTES = 32 * 1024 * 1024         # 이만큼 거슬러도 기준 시각에 못 닿으면 전체 읽기로 폴백


def _last_row_dt(ws, scan=100):
    """sensor_log 마지막 scan개 행 중 가장 늦은 시각(정렬이 살짝 어긋나 있어도 안전하게)."""
    best = None
    for row_idx in range(ws.max_row, max(1, ws.max_row - scan), -1):
        ts = _parse_dt(ws.cell(row=row_idx, column=1).value)
        if ts is not None and (best is None or ts > best):
            best = ts
    return best


def _first_row_dt(ws, scan=100):
    """sensor_log 처음 scan개 행 중 가장 이른 시각."""
    best = None
    for row_idx in range(2, min(ws.max_row, scan + 1) + 1):
        ts = _parse_dt(ws.cell(row=row_idx, column=1).value)
        if ts is not None and (best is None or ts < best):
            best = ts
    return best


def _read_txt_tail(cutoff):
    """WH24Data.txt 끝에서부터 cutoff 이전 시각이 포함될 때까지 거슬러 읽어 줄 목록을 돌려준다.
    TAIL_MAX_BYTES 안에서 cutoff에 못 닿으면 None(호출 측이 전체 읽기로 폴백)."""
    size = TAIL_INITIAL_BYTES
    while True:
        _log(f"txt 열기 (tail {size // 1024}KB)")
        with open(TXT_PATH, "rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            start = max(0, file_size - size)
            f.seek(start)
            raw = f.read()
        _log(f"txt 닫기 (파일 {file_size}B 중 offset {start}부터 {len(raw)}B 읽음)")

        if start > 0:
            # 중간에서 시작했으니 첫 줄(멀티바이트 문자 중간일 수도 있음)은 버린다
            nl = raw.find(b"\n")
            raw = raw[nl + 1:] if nl >= 0 else b""
        # 텍스트 모드 for line in f(universal newlines)와 같은 기준으로 줄을 나눈다
        lines = raw.decode("cp949", errors="ignore").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        # 마지막 원소는 개행 뒤 빈 문자열이거나, UART가 아직 쓰는 중인 미완성 줄 -> 다음 실행에서 읽는다
        lines = lines[:-1]

        if start == 0:
            return lines  # 파일 전체가 들어왔다
        first = next((_parse_dt(r[0]) for r in map(parse_line, lines) if r), None)
        if first is not None and first <= cutoff:
            return lines
        if size >= TAIL_MAX_BYTES:
            _log(f"tail {size // 1024}KB로 기준 시각({cutoff})까지 못 닿음(첫 행 {first}) - 전체 읽기로 폴백")
            return None
        size *= 2


def merge_solar(ws, header):
    """각 행의 시각에 가장 가까운 일사량을 solar_radiation_wm2 컬럼에 채운다.

    - 이미 값이 있는 행은 건드리지 않는다 (몇 번 재실행해도 안전)
    - 일사량 로그 시작 이전의 과거 행은 채울 값이 없으므로, 아래에서 위로
      훑다가 그 지점에서 멈춘다 (22만 행 전체를 매번 훑지 않기 위해)
    """
    samples = _load_solar_samples()
    if not samples or "solar_radiation_wm2" not in header:
        return 0

    col = header.index("solar_radiation_wm2") + 1
    times = [item[0] for item in samples]
    earliest = times[0] - timedelta(seconds=SOLAR_MATCH_TOLERANCE_SEC)

    filled = 0
    for row_idx in range(ws.max_row, 1, -1):
        ts = _parse_dt(ws.cell(row=row_idx, column=1).value)
        if ts is None:
            continue
        if ts < earliest:
            break
        if ws.cell(row=row_idx, column=col).value is not None:
            continue
        value = _nearest_value(times, samples, ts)
        if value is not None:
            ws.cell(row=row_idx, column=col).value = value
            filled += 1
    return filled


# 2026-10-08: sensor_log.xlsx 자동 로테이션. 34만 행 xlsx를 매번 통째로 열고 저장하느라 collector가
# ~1GB/4분을 쓰던 문제를 1회성 트리밍(10/1 이전 -> archive CSV)으로 해결했고, 다시 커지지 않도록 하루 1번
# 마지막 행 날짜 7일 전 00:00 이전 행을 월별 CSV로 옮긴다. CSV 추가+검증이 끝난 뒤에만 xlsx에서 지우고,
# 어느 단계든 실패하면 xlsx 행은 그대로 둔 채 로그만 남긴다(상태 파일을 안 갱신하므로 다음 실행에서 재시도).
ARCHIVE_DIR = os.path.join(os.path.dirname(XLSX_PATH), "archive", "sensor_log")
ROTATE_STATE_PATH = os.path.join(os.path.dirname(XLSX_PATH), "tmp", "sensor_log_rotate_state.txt")
# [rotate] 결과는 auto_push.log와 별도로 여기에도 남긴다 - 매일 첫 실행은 출력을 남기지 않는
# WH24Collector(00:00 직접 실행)라서 auto_push.log만으로는 결과를 볼 수 없다.
ROTATE_LOG_PATH = os.path.join(os.path.dirname(XLSX_PATH), "tmp", "sensor_log_rotate.log")
ROTATE_KEEP_DAYS = 7
ARCHIVE_COLS = 12


def _rotate_log(msg):
    _log(msg)
    try:
        os.makedirs(os.path.dirname(ROTATE_LOG_PATH), exist_ok=True)
        now = datetime.now()
        with open(ROTATE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{now:%Y-%m-%d %H:%M:%S}.{now.microsecond // 1000:03d}] pid={os.getpid()} {msg}\n")
    except OSError:
        pass


def _rotate_due():
    """상태 파일 첫 줄(마지막 성공 날짜)이 오늘이 아니면 오늘 첫 실행 -> 로테이션 대상."""
    try:
        with open(ROTATE_STATE_PATH, encoding="utf-8") as f:
            return f.readline().strip() != datetime.now().strftime("%Y-%m-%d")
    except OSError:
        return True


def _rotate_mark_done(summary):
    os.makedirs(os.path.dirname(ROTATE_STATE_PATH), exist_ok=True)
    with open(ROTATE_STATE_PATH, "w", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d}\n{datetime.now():%Y-%m-%d %H:%M:%S} {summary}\n")


def _csv_stats(path):
    """월별 CSV의 (데이터 행수, 마지막 시각, 개행으로 끝나는지). 없으면 None. 줄 단위 스트리밍."""
    if not os.path.exists(path):
        return None
    count, last = 0, None
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # 헤더
        for row in reader:
            if row:
                count += 1
                last = row[0]
    with open(path, "rb") as f:
        f.seek(-1, os.SEEK_END)
        ends_nl = f.read(1) == b"\n"
    return count, (_parse_dt(last) if last else None), ends_nl


def _csv_times(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        return {_parse_dt(row[0]) for row in reader if row}


def _rotate_write_month(path, header, rows):
    """월별 CSV에 행을 덧붙인다. 새 파일이면 UTF-8 BOM + 헤더부터."""
    new_file = not os.path.exists(path)
    with open(path, "w" if new_file else "a", encoding="utf-8-sig" if new_file else "utf-8", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(header)
        writer.writerows(rows)
        f.flush()
        os.fsync(f.fileno())


def rotate(ws, header):
    """기준 시각 이전 행을 월별 CSV로 옮기고 ws에서 지운다. 실패하면 예외(ws는 그대로).
    대상은 2행부터 이어지는 '기준 시각 이전' 연속 구간만이다(정렬이 어긋난 뒤쪽 행은 건드리지 않음)."""
    last_dt = _last_row_dt(ws)
    if last_dt is None:
        raise RuntimeError("sensor_log 마지막 행 시각을 알 수 없음")
    cutoff = datetime.combine(last_dt.date() - timedelta(days=ROTATE_KEEP_DAYS), datetime.min.time())

    months = {}
    prefix = 0
    prev = None
    for row in ws.iter_rows(min_row=2, max_col=ARCHIVE_COLS, values_only=True):
        dt = _parse_dt(row[0]) if row[0] is not None else None
        if dt is None or dt >= cutoff:
            break
        if prev is not None and dt <= prev:
            raise RuntimeError(f"시각 역순/중복: {prev} -> {dt} (행 {prefix + 2})")
        prev = dt
        values = list(row) + [None] * (ARCHIVE_COLS - len(row))
        months.setdefault(dt.strftime("%Y-%m"), []).append((dt, values))
        prefix += 1
    if prefix == 0:
        return f"기준 {cutoff}: 대상 없음"

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    archived = 0
    for month, items in sorted(months.items()):
        path = os.path.join(ARCHIVE_DIR, f"sensor_log_{month}.csv")
        before = _csv_stats(path)
        if before and not before[2]:
            raise RuntimeError(f"{os.path.basename(path)} 끝이 개행이 아님(이전 쓰기 중단 의심) - 수동 확인 필요")
        csv_last = before[1] if before else None
        new_rows = [v for dt, v in items if csv_last is None or dt > csv_last]
        already = [dt for dt, v in items if not (csv_last is None or dt > csv_last)]
        if already:
            # 이전 실행이 CSV 추가 후 xlsx 저장 전에 실패한 경우 - CSV에 실제로 있는지 확인하고 넘어간다
            present = _csv_times(path)
            missing = [d for d in already if d not in present]
            if missing:
                raise RuntimeError(f"{month}: CSV 마지막 시각({csv_last}) 이전인데 CSV에 없는 행 {len(missing)}개(첫 {missing[0]})")
        if new_rows:
            _rotate_write_month(path, list(header[:ARCHIVE_COLS]), new_rows)
            after = _csv_stats(path)
            expect = (before[0] if before else 0) + len(new_rows)
            if after is None or after[0] != expect or after[1] != _parse_dt(new_rows[-1][0]) or not after[2]:
                raise RuntimeError(f"{month}: CSV 추가 검증 실패(행 {after and after[0]}, 기대 {expect})")
            archived += len(new_rows)

    # 여기까지 왔으면 대상 행은 모두 CSV에 있다 -> 이제서야 xlsx에서 제거
    try:
        ws.delete_rows(2, prefix)
    except BaseException as e:
        # ws가 중간 상태일 수 있으니 저장하지 않고 종료(원본 xlsx 보존, 다음 실행에서 재시도)
        _rotate_log(f"[rotate] xlsx 행 제거 중 예외({type(e).__name__}: {e}) - 저장하지 않고 종료")
        raise SystemExit(1)
    return f"기준 {cutoff}: 아카이브 {archived}행, xlsx 제거 {prefix}행, 남은 {ws.max_row - 1}행"


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
            for col_name in ("wind_direction", "uv", "uvi", "rainfall_mm", "solar_radiation_wm2"):
                if col_name not in header:
                    ws.cell(row=1, column=len(header) + 1, value=col_name)
                    header.append(col_name)
        else:
            wb = openpyxl.Workbook()
            ws = wb.active
            header = ["datetime","temperature","humidity","wind_speed","rainfall","light_lux","crc_status","wind_direction","uv","uvi","rainfall_mm","solar_radiation_wm2"]
            ws.append(header)

        _log(f"xlsx 로드 완료 (max_row={ws.max_row})")

        existing = set()
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0]:
                existing.add(str(row[0]))

        last_dt = _last_row_dt(ws)
        lines = None
        if last_dt is not None:
            cutoff = min(datetime.now() - TAIL_LOOKBACK, last_dt - TAIL_MARGIN)
            lines = _read_txt_tail(cutoff)
        else:
            _log("sensor_log 마지막 행 시각을 알 수 없음 - 전체 읽기")

        # 트리밍/로테이션으로 archive CSV로 옮긴 행이 txt에서 다시 들어오지 않도록, xlsx 첫 행보다
        # 오래된 txt 행은 받지 않는다(트리밍 전에는 xlsx 첫 행 = txt 첫 행이라 기존 동작과 같음).
        first_dt = _first_row_dt(ws)
        skipped_old = 0

        def _add(line):
            nonlocal skipped_old
            if line.strip() == "":
                return 0
            row = parse_line(line)
            if row and str(row[0]) not in existing:
                dt = _parse_dt(row[0])
                if first_dt is not None and dt is not None and dt < first_dt:
                    skipped_old += 1
                    return 0
                ws.append(row)
                existing.add(str(row[0]))
                return 1
            return 0

        new_count = 0
        if lines is not None:
            for line in lines:
                new_count += _add(line)
            read_lines = len(lines)
        else:
            # 폴백: 기존 방식 그대로(파일 전체를 줄 단위로 읽음)
            _log("txt 열기 (전체)")
            read_lines = 0
            with open(TXT_PATH, "r", encoding="cp949", errors="ignore") as f:
                for line in f:
                    read_lines += 1
                    new_count += _add(line)
            _log("txt 닫기 (전체)")
        _log(f"txt 읽은 줄 {read_lines}, 새 행 {new_count}, xlsx 첫 행({first_dt}) 이전이라 건너뜀 {skipped_old}")

        apply_interpolation(ws)
        solar_filled = merge_solar(ws, header)

        rotate_summary = None
        if _rotate_due():
            t_rot = time.time()
            try:
                rotate_summary = rotate(ws, header)
                _rotate_log(f"[rotate] {rotate_summary}, {time.time() - t_rot:.1f}초")
            except Exception as e:
                _rotate_log(f"[rotate] 실패 - xlsx 행은 그대로, 다음 실행에서 재시도 ({type(e).__name__}: {e}), {time.time() - t_rot:.1f}초")

        _safe_save(wb)
        if rotate_summary is not None:
            _rotate_mark_done(rotate_summary)  # 저장까지 성공해야 오늘 완료로 기록
        print(f"완료! 새로 추가된 데이터: {new_count}개, 일사량 병합: {solar_filled}개")
    finally:
        _release_lock()

if __name__ == "__main__":
    main()