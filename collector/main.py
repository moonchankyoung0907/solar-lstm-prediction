"""군산 태양광 발전소 - 데이터 수집기 진입점

실행 방법:
    python -m collector.main              # 정상 수집 루프
    python -m collector.main --once       # 1회만 수집 후 종료 (테스트용)
    python -m collector.main --dry-run    # 포트 없이 더미 데이터로 xlsx 기록 테스트

의존 패키지:
    pip install pyserial openpyxl
"""

import argparse
import logging
import sys
import time
from datetime import datetime

from collector.collector_config import load
from collector.protocols.bms_reader import BmsData, BmsReader
from collector.protocols.meter_reader import MeterData, MeterReader
from collector.protocols.weather_reader import WeatherData, WeatherReader
from collector.xlsx_writer import append_row


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def collect_once(
    bms_reader: BmsReader,
    weather_reader: WeatherReader,
    meter_reader: MeterReader,
) -> tuple[BmsData, WeatherData, MeterData]:
    bms     = bms_reader.read()
    weather = weather_reader.read()
    meter   = meter_reader.read()

    if not bms.ok:
        logging.getLogger(__name__).warning("BMS 수집 실패")
    if not weather.ok:
        logging.getLogger(__name__).warning("기상센서 수집 실패")
    if not meter.ok:
        logging.getLogger(__name__).warning("전력량계 수집 실패")

    return bms, weather, meter


def _dummy_data() -> tuple[BmsData, WeatherData, MeterData]:
    """--dry-run 용 더미 데이터"""
    bms = BmsData(
        voltage_v=384.0, current_a=-10.5, soc_pct=78.0,
        cell_temp_max_c=28.3, cell_temp_min_c=26.1,
        cell_volt_max_v=3.72, cell_volt_min_v=3.68,
        cycle_count=42, alarm_flags=0, protect_flags=0, ok=True,
    )
    weather = WeatherData(
        device_id=1, irradiance_wm2=650.3, temperature_c=21.4,
        wind_speed_ms=2.7, wind_dir_deg=180.0, humidity_pct=55.0,
        pressure_hpa=1013.0, status=0, ok=True,
    )
    meter = MeterData(device_addr=1, power_kw=58.2, energy_kwh=12340.5, ok=True)
    return bms, weather, meter


def main() -> None:
    parser = argparse.ArgumentParser(description="군산 태양광 발전소 데이터 수집기")
    parser.add_argument("--once",    action="store_true", help="1회 수집 후 종료")
    parser.add_argument("--dry-run", action="store_true", help="더미 데이터로 xlsx 기록 테스트")
    args = parser.parse_args()

    bms_cfg, weather_cfg, meter_cfg, coll_cfg = load()
    _setup_logging(coll_cfg.log_level)
    logger = logging.getLogger(__name__)

    logger.info("=== 군산 태양광 데이터 수집기 시작 ===")
    logger.info("BMS    : %s @ %dbps", bms_cfg.port, bms_cfg.baudrate)
    logger.info("Weather: %s @ %dbps", weather_cfg.port, weather_cfg.baudrate)
    logger.info("Meter  : %s @ %dbps", meter_cfg.port, meter_cfg.baudrate)
    logger.info("xlsx   : %s", coll_cfg.xlsx_path)
    logger.info("주기   : %d초", coll_cfg.interval_sec)

    if args.dry_run:
        logger.info("[dry-run] 더미 데이터로 실행합니다 (실제 COM 포트 불필요)")
        bms, weather, meter = _dummy_data()
        append_row(coll_cfg.xlsx_path, datetime.now(), meter, weather, bms)
        logger.info("[dry-run] 완료")
        return

    with (
        BmsReader(bms_cfg)         as bms_r,
        WeatherReader(weather_cfg) as weather_r,
        MeterReader(meter_cfg)     as meter_r,
    ):
        while True:
            ts = datetime.now()
            try:
                bms, weather, meter = collect_once(bms_r, weather_r, meter_r)
                append_row(coll_cfg.xlsx_path, ts, meter, weather, bms)
            except Exception as exc:
                logger.error("수집 루프 오류: %s", exc)

            if args.once:
                break

            time.sleep(coll_cfg.interval_sec)


if __name__ == "__main__":
    main()
