"""태양광 시뮬레이터 — 센서·예측·인버터 데이터 생성"""

import logging
from datetime import datetime, timedelta

import numpy as np

from solar_lstm_sim.config import (
    SYSTEM_CAPACITY_KW,
    INVERTER_EFFICIENCY,
    PERFORMANCE_RATIO,
    NOCT,
    SENSOR_IRR_NOISE_RATIO,
    FORECAST_IRR_NOISE_STD,
    FORECAST_TEMP_NOISE_STD,
    INVERTER_NOISE_RATIO,
    PEAK_IRRADIANCE,
    SEASONAL_TEMP,
    FUTURE_STEPS,
)

logger = logging.getLogger(__name__)


class SolarSimulator:
    """Python 시뮬레이터 — 추후 실 센서/API로 교체"""

    def __init__(self, capacity_kw: float = SYSTEM_CAPACITY_KW):
        self.capacity = capacity_kw

    # ── 공통 유틸 ───────────────────────────────────
    @staticmethod
    def _get_season(month: int) -> str:
        if month in (3, 4, 5):
            return "spring"
        elif month in (6, 7, 8):
            return "summer"
        elif month in (9, 10, 11):
            return "autumn"
        else:
            return "winter"

    @staticmethod
    def _base_irradiance(hour: float) -> float:
        """가우시안 일사량 곡선 (정오 피크)"""
        if hour < 6 or hour > 19:
            return 0.0
        return PEAK_IRRADIANCE * np.exp(-0.5 * ((hour - 12.5) / 3.0) ** 2)

    def _base_temp(self, dt: datetime) -> float:
        season = self._get_season(dt.month)
        return float(SEASONAL_TEMP[season])

    # ── sensor_simulator ────────────────────────────
    def sensor_simulator(self, dt: datetime | None = None) -> dict:
        """현재 시각 실측값 생성"""
        if dt is None:
            dt = datetime.now().replace(minute=0, second=0, microsecond=0)

        hour = dt.hour + dt.minute / 60.0
        base_irr = self._base_irradiance(hour)

        # 일사량 노이즈
        noise = np.random.uniform(-SENSOR_IRR_NOISE_RATIO, SENSOR_IRR_NOISE_RATIO)
        irradiance = float(np.clip(base_irr * (1 + noise), 0, PEAK_IRRADIANCE))

        # 외기 온도
        temp_air = self._base_temp(dt) + np.random.normal(0, FORECAST_TEMP_NOISE_STD)
        temp_air = float(np.clip(temp_air, -10, 45))

        # 모듈 온도 (NOCT 공식)
        temp_module = temp_air + (NOCT - 20) / 800.0 * irradiance
        temp_module = float(np.clip(temp_module, -10, 85))

        # 물리 발전량
        power = self._compute_power(irradiance)

        return {
            "timestamp": dt,
            "irradiance": round(irradiance, 2),
            "temp_module": round(temp_module, 2),
            "temp_air": round(temp_air, 2),
            "power_actual": round(power, 4),
        }

    # ── forecast_simulator ──────────────────────────
    def forecast_simulator(self, dt: datetime | None = None) -> list[dict]:
        """미래 10시간 예측값 생성 (약간 더 큰 노이즈)"""
        if dt is None:
            dt = datetime.now().replace(minute=0, second=0, microsecond=0)

        forecasts = []
        for h in range(1, FUTURE_STEPS + 1):
            ft = dt + timedelta(hours=h)
            hour = ft.hour + ft.minute / 60.0

            # 일사량
            base_irr = self._base_irradiance(hour)
            irr = float(np.clip(base_irr + np.random.normal(0, FORECAST_IRR_NOISE_STD), 0, PEAK_IRRADIANCE))

            # 기온
            temp = self._base_temp(ft) + np.random.normal(0, FORECAST_TEMP_NOISE_STD)
            temp = float(np.clip(temp, -10, 45))

            forecasts.append({
                "created_at": dt,
                "forecast_time": ft,
                "irradiance_forecast": round(irr, 2),
                "temp_forecast": round(temp, 2),
                "horizon": h,
            })
        return forecasts

    # ── inverter_simulator ──────────────────────────
    def inverter_simulator(self, irradiance: float) -> float:
        """발전량 = cap × (irr/1000) × η × PR + 노이즈"""
        if irradiance <= 0:
            return 0.0
        base_power = self.capacity * (irradiance / 1000.0) * INVERTER_EFFICIENCY * PERFORMANCE_RATIO
        noise = np.random.uniform(-INVERTER_NOISE_RATIO, INVERTER_NOISE_RATIO)
        return float(max(0.0, round(base_power * (1 + noise), 4)))

    def _compute_power(self, irradiance: float) -> float:
        return self.inverter_simulator(irradiance)

    # ── 부트스트랩: 대량 데이터 생성 ───────────────
    def generate_historical_data(self, days: int = 90, start_dt: datetime | None = None):
        """days일 분량의 1시간 간격 센서+예측 데이터 생성"""
        if start_dt is None:
            start_dt = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=days)

        sensor_rows: list[dict] = []
        forecast_rows: list[dict] = []

        current = start_dt
        end = start_dt + timedelta(days=days)

        while current < end:
            # 센서 데이터
            sensor = self.sensor_simulator(current)
            sensor_rows.append(sensor)

            # 예측 데이터
            forecasts = self.forecast_simulator(current)
            forecast_rows.extend(forecasts)

            current += timedelta(hours=1)

        logger.info("Generated %d sensor rows and %d forecast rows for %d days.",
                     len(sensor_rows), len(forecast_rows), days)
        return sensor_rows, forecast_rows
