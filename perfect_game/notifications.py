"""Email notification helpers for Perfect Game schedule changes."""

import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from shared.config import SMTP_HOST, SMTP_PORT, SMTP_TIMEOUT

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")


def is_recent_past_game(game, hours=48):
    """Return True for a Past game dated within the recent alert window."""
    if game.get("Type") != "Past":
        return False
    date_str = (game.get("Date") or "").strip()
    if not date_str:
        return False
    try:
        game_date = datetime.strptime(f"{date_str} {datetime.now().year}", "%b %d %Y")
    except ValueError:
        return False
    game_end_approx = game_date.replace(hour=23, minute=59)
    return game_end_approx >= datetime.now() - timedelta(hours=hours)


def _filter_alert_games(games):
    now = datetime.now()
    cutoff = now + timedelta(days=7)
    current_year = now.year

    filtered = []
    for game in games:
        if game.get("Type") == "Past":
            filtered.append(game)
            continue
        date_str = (game.get("Date") or "").strip()
        try:
            game_date = datetime.strptime(f"{date_str} {current_year}", "%b %d %Y")
        except ValueError:
            filtered.append(game)
            continue
        if game_date <= cutoff:
            filtered.append(game)
    return filtered


def build_alert_email(games, player_name="Your Player Name"):
    """Build an HTML email listing affected games."""
    rows = ""
    for game in _filter_alert_games(games):
        time_or_result = (
            game.get("Score/Result")
            if game.get("Type") == "Past"
            else game.get("Time", "TBD")
        )
        rows += f"""
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">{game.get('Date', 'TBD')}</td>
                <td style="padding:8px;border:1px solid #ddd;">{time_or_result}</td>
                <td style="padding:8px;border:1px solid #ddd;">{game.get('Opponent', '?')}</td>
                <td style="padding:8px;border:1px solid #ddd;">{game.get('Location', 'TBD')}</td>
            </tr>"""

    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;color:#333;">
        <h2 style="color:#1a3a5c;">⚾ Schedule Alert for {player_name}</h2>
        <table style="border-collapse:collapse;width:100%;max-width:700px;">
            <thead>
                <tr style="background-color:#1a3a5c;color:white;">
                    <th style="padding:10px;border:1px solid #ddd;">Date</th>
                    <th style="padding:10px;border:1px solid #ddd;">Time / Result</th>
                    <th style="padding:10px;border:1px solid #ddd;">Opponent</th>
                    <th style="padding:10px;border:1px solid #ddd;">Location</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        <br>
        <p style="font-size:12px;color:#888;">
            Checked at {datetime.now().strftime('%b %d, %Y %I:%M %p')} — Perfect Game Monitor
        </p>
    </body>
    </html>
    """


def send_alert(to_addr, subject, html_body):
    """Send an HTML alert email via Gmail SMTP."""
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        return False

    recipients = [addr.strip() for addr in to_addr.split(",") if addr.strip()]
    if not recipients:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as server:
            server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, recipients, msg.as_string())
        return True
    except smtplib.SMTPResponseException as e:
        return 200 <= e.smtp_code < 300
    except Exception:
        return False
