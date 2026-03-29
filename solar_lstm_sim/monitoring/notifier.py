"""이메일 알람 — SMTP 미설정시 로그만 출력"""

import logging
import smtplib
from email.mime.text import MIMEText

from solar_lstm_sim.config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    ALERT_RECIPIENT,
)

logger = logging.getLogger(__name__)


def send_alert(subject: str, body: str):
    """이메일 알람 발송. SMTP 미설정시 로그만 남김."""
    if not SMTP_HOST or not SMTP_USER or not ALERT_RECIPIENT:
        logger.warning("[ALERT] %s — %s", subject, body)
        return

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[Solar LSTM] {subject}"
        msg["From"] = SMTP_USER
        msg["To"] = ALERT_RECIPIENT

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info("Alert email sent: %s", subject)
    except Exception as e:
        logger.error("Failed to send alert email: %s", e)
        logger.warning("[ALERT] %s — %s", subject, body)
