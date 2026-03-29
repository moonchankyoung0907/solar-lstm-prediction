"""MySQL CRUD 핸들러 — 5개 테이블 관리"""

import logging
from datetime import datetime
from typing import Optional

import pymysql
import pymysql.cursors

from solar_lstm_sim.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

logger = logging.getLogger(__name__)


class DBHandler:
    """MySQL 데이터베이스 핸들러"""

    def __init__(self):
        self.conn_params = dict(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

    # ── 연결 ────────────────────────────────────────
    def _connect(self, use_db: bool = True):
        params = dict(self.conn_params)
        if use_db:
            params["database"] = DB_NAME
        return pymysql.connect(**params)

    # ── 데이터베이스 / 테이블 생성 ──────────────────
    def create_database(self):
        conn = self._connect(use_db=False)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            conn.commit()
            logger.info("Database '%s' created or already exists.", DB_NAME)
        finally:
            conn.close()

    def create_tables(self):
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sensor_data (
                        id            INT AUTO_INCREMENT PRIMARY KEY,
                        timestamp     DATETIME NOT NULL,
                        irradiance    FLOAT,
                        temp_module   FLOAT,
                        temp_air      FLOAT,
                        power_actual  FLOAT,
                        is_simulated  TINYINT(1) DEFAULT 1,
                        INDEX idx_ts (timestamp)
                    ) ENGINE=InnoDB
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS forecast_data (
                        id                    INT AUTO_INCREMENT PRIMARY KEY,
                        created_at            DATETIME NOT NULL,
                        forecast_time         DATETIME NOT NULL,
                        irradiance_forecast   FLOAT,
                        temp_forecast         FLOAT,
                        horizon               INT,
                        is_simulated          TINYINT(1) DEFAULT 1,
                        INDEX idx_created (created_at),
                        INDEX idx_forecast (forecast_time)
                    ) ENGINE=InnoDB
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS prediction_result (
                        id                INT AUTO_INCREMENT PRIMARY KEY,
                        created_at        DATETIME NOT NULL,
                        target_time       DATETIME NOT NULL,
                        power_lstm        FLOAT,
                        confidence_lower  FLOAT,
                        confidence_upper  FLOAT,
                        INDEX idx_created (created_at),
                        INDEX idx_target (target_time)
                    ) ENGINE=InnoDB
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS error_log (
                        id              INT AUTO_INCREMENT PRIMARY KEY,
                        timestamp       DATETIME NOT NULL,
                        power_predicted FLOAT,
                        power_actual    FLOAT,
                        mape            FLOAT,
                        rmse            FLOAT,
                        INDEX idx_ts (timestamp)
                    ) ENGINE=InnoDB
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS model_log (
                        id          INT AUTO_INCREMENT PRIMARY KEY,
                        trained_at  DATETIME NOT NULL,
                        mape_new    FLOAT,
                        mape_old    FLOAT,
                        adopted     TINYINT(1),
                        model_path  VARCHAR(512)
                    ) ENGINE=InnoDB
                """)
            conn.commit()
            logger.info("All tables created or already exist.")
        finally:
            conn.close()

    # ── INSERT ──────────────────────────────────────
    def insert_sensor_data(self, timestamp: datetime, irradiance: float,
                           temp_module: float, temp_air: float,
                           power_actual: float, is_simulated: bool = True):
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO sensor_data (timestamp, irradiance, temp_module, temp_air, power_actual, is_simulated) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (timestamp, irradiance, temp_module, temp_air, power_actual, int(is_simulated)),
                )
            conn.commit()
        finally:
            conn.close()

    def insert_forecast_data(self, created_at: datetime, forecast_time: datetime,
                             irradiance_forecast: float, temp_forecast: float,
                             horizon: int, is_simulated: bool = True):
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO forecast_data (created_at, forecast_time, irradiance_forecast, temp_forecast, horizon, is_simulated) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (created_at, forecast_time, irradiance_forecast, temp_forecast, horizon, int(is_simulated)),
                )
            conn.commit()
        finally:
            conn.close()

    def insert_prediction(self, created_at: datetime, target_time: datetime,
                          power_lstm: float, confidence_lower: float,
                          confidence_upper: float):
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO prediction_result (created_at, target_time, power_lstm, confidence_lower, confidence_upper) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (created_at, target_time, power_lstm, confidence_lower, confidence_upper),
                )
            conn.commit()
        finally:
            conn.close()

    def insert_error_log(self, timestamp: datetime, power_predicted: float,
                         power_actual: float, mape: float, rmse: float):
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO error_log (timestamp, power_predicted, power_actual, mape, rmse) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (timestamp, power_predicted, power_actual, mape, rmse),
                )
            conn.commit()
        finally:
            conn.close()

    def insert_model_log(self, trained_at: datetime, mape_new: float,
                         mape_old: float, adopted: bool, model_path: str):
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO model_log (trained_at, mape_new, mape_old, adopted, model_path) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (trained_at, mape_new, mape_old, int(adopted), model_path),
                )
            conn.commit()
        finally:
            conn.close()

    # ── BULK INSERT (부트스트랩 성능) ───────────────
    def bulk_insert_sensor_data(self, rows: list[dict]):
        """rows: list of dict with keys timestamp, irradiance, temp_module, temp_air, power_actual"""
        if not rows:
            return
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO sensor_data (timestamp, irradiance, temp_module, temp_air, power_actual, is_simulated) "
                    "VALUES (%(timestamp)s, %(irradiance)s, %(temp_module)s, %(temp_air)s, %(power_actual)s, 1)",
                    rows,
                )
            conn.commit()
            logger.info("Bulk inserted %d sensor rows.", len(rows))
        finally:
            conn.close()

    def bulk_insert_forecast_data(self, rows: list[dict]):
        """rows: list of dict with keys created_at, forecast_time, irradiance_forecast, temp_forecast, horizon"""
        if not rows:
            return
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO forecast_data (created_at, forecast_time, irradiance_forecast, temp_forecast, horizon, is_simulated) "
                    "VALUES (%(created_at)s, %(forecast_time)s, %(irradiance_forecast)s, %(temp_forecast)s, %(horizon)s, 1)",
                    rows,
                )
            conn.commit()
            logger.info("Bulk inserted %d forecast rows.", len(rows))
        finally:
            conn.close()

    # ── SELECT ──────────────────────────────────────
    def get_sensor_data(self, hours: int = 24, before: Optional[datetime] = None) -> list[dict]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                if before is None:
                    cur.execute(
                        "SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT %s",
                        (hours,),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM sensor_data WHERE timestamp <= %s ORDER BY timestamp DESC LIMIT %s",
                        (before, hours),
                    )
                return list(reversed(cur.fetchall()))
        finally:
            conn.close()

    def get_latest_sensor(self) -> Optional[dict]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT 1")
                return cur.fetchone()
        finally:
            conn.close()

    def get_forecast_data(self, created_at: Optional[datetime] = None) -> list[dict]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                if created_at is None:
                    cur.execute(
                        "SELECT * FROM forecast_data ORDER BY created_at DESC, horizon ASC LIMIT 10"
                    )
                else:
                    cur.execute(
                        "SELECT * FROM forecast_data WHERE created_at = %s ORDER BY horizon ASC",
                        (created_at,),
                    )
                rows = cur.fetchall()
                return list(sorted(rows, key=lambda r: r["horizon"]))
        finally:
            conn.close()

    def get_latest_predictions(self) -> list[dict]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT created_at FROM prediction_result ORDER BY created_at DESC LIMIT 1"
                )
                row = cur.fetchone()
                if row is None:
                    return []
                cur.execute(
                    "SELECT * FROM prediction_result WHERE created_at = %s ORDER BY target_time ASC",
                    (row["created_at"],),
                )
                return cur.fetchall()
        finally:
            conn.close()

    def get_latest_metrics(self) -> Optional[dict]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM error_log ORDER BY timestamp DESC LIMIT 1")
                return cur.fetchone()
        finally:
            conn.close()

    def get_all_sensor_data(self, days: int = 90) -> list[dict]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM sensor_data WHERE timestamp >= DATE_SUB(NOW(), INTERVAL %s DAY) ORDER BY timestamp ASC",
                    (days,),
                )
                return cur.fetchall()
        finally:
            conn.close()

    def get_all_forecast_data(self, days: int = 90) -> list[dict]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM forecast_data WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY) ORDER BY created_at ASC, horizon ASC",
                    (days,),
                )
                return cur.fetchall()
        finally:
            conn.close()

    def get_sensor_count(self) -> int:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM sensor_data")
                return cur.fetchone()["cnt"]
        finally:
            conn.close()

    def get_predictions_for_evaluation(self, target_time: datetime) -> list[dict]:
        """target_time에 해당하는 과거 예측값 조회"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM prediction_result WHERE target_time = %s ORDER BY created_at DESC LIMIT 1",
                    (target_time,),
                )
                result = cur.fetchone()
                return [result] if result else []
        finally:
            conn.close()
