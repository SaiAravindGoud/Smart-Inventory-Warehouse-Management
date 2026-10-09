
import os
import smtplib
import logging
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv


logger = logging.getLogger(__name__)

# Load the project's root .env file.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def send_email(
    to_email: str,
    subject: str,
    body: str,
) -> bool:
    """Send a plain-text email using the configured SMTP server."""

    host = os.getenv("SMTP_HOST")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("SMTP_FROM_EMAIL") or username
    from_name = os.getenv("SMTP_FROM_NAME", "Smart Inventory System")
    port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() in {
        "1", "true", "yes", "on"
    }

    if not host or not from_email:
        logger.error("Email not sent: SMTP host or sender email is missing.")
        return False

    if not to_email or not to_email.strip():
        logger.error("Email not sent: recipient email is missing.")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = to_email.strip()
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()

            if use_tls:
                server.starttls()
                server.ehlo()

            if username and password:
                server.login(username, password)

            server.send_message(message)

        logger.info("Email sent successfully to %s", to_email)
        return True

    except (OSError, smtplib.SMTPException, ValueError):
        logger.exception("Failed to send email to %s", to_email)
        return False
