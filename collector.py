import os
import openpyxl

TXT_PATH = r"C:\Users\sejae\Desktop\웨더게이트 소프트웨어\WH-2300S PC소프트웨어 25.03 (유저용)\WH-2300S 관련 User 제공자료\WH-2300S display software\WH24Data.txt"
XLSX_PATH = r"C:\Users\sejae\Desktop\sensor_log.xlsx"

def parse_line(line):
    try:
        parts = line.strip().split(",")
        if len(parts) < 10:
            return None
        dt = parts[0].strip()
        temp = parts[2].strip().replace("▲C","").replace("℃","").strip()
        humidity = parts[3].strip().replace("%","").strip()
        wind = parts[4].strip().replace("m/s","").strip()
        rain = parts[6].strip()
        lux = parts[9].strip().replace("lux","").strip()
        # CRC 에러 체크
        crc = "OK"
        for part in parts:
            if "CRC" in part or "ERROR" in part:
                crc = "ERROR"
                break
        return [dt, float(temp), float(humidity), float(wind), float(rain), float(lux), crc]
    except:
        return None

def apply_interpolation(ws):
    max_row = ws.max_row
    for row_idx in range(2, max_row + 1):
        crc = ws.cell(row=row_idx, column=7).value
        if crc == "ERROR":
            for col in range(2, 7):
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
    if os.path.exists(XLSX_PATH):
        wb = openpyxl.load_workbook(XLSX_PATH)
        ws = wb.active
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["datetime","temperature","humidity","wind_speed","rainfall","light_lux","crc_status"])

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

if __name__ == "__main__":
    main()