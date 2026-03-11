#!/usr/bin/env python3
"""
email_schedule.py - Emails the next game schedule for a given player.

Reads team_schedule.json, filters for upcoming games in the next 7 days, and sends
a nicely formatted email via Gmail SMTP using credentials from .env.

Requires the .venv virtual environment (setup_cron.sh handles this for cron).

Usage:
    python3 email_schedule.py
    python3 email_schedule.py --schedule team_schedule.json --to your@email.com
"""

import argparse
import json
import os
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")


def load_schedule(filepath="team_schedule.json"):
    """Load the schedule JSON file."""
    with open(filepath, "r") as f:
        return json.load(f)


def filter_upcoming(games):
    """Return upcoming games within the next 7 days."""
    now = datetime.now()
    cutoff = now + timedelta(days=7)
    current_year = now.year
    result = []
    for g in games:
        if g.get("Type") != "Upcoming":
            continue
        date_str = (g.get("Date") or "").strip()
        try:
            game_date = datetime.strptime(f"{date_str} {current_year}", "%b %d %Y")
        except ValueError:
            result.append(g)  # keep if date unparseable
            continue
        if game_date <= cutoff:
            result.append(g)
    return result


def build_email_body(games, player_name="Your Player Name"):
    """Build a clean HTML email body for upcoming games in the next 7 days."""
    games = filter_upcoming(games)
    if not games:
        return "<p>No upcoming games found in the schedule.</p>"

    rows = ""
    for g in games:
        date = g.get("Date") or "TBD"
        time = g.get("Time") or "TBD"
        opponent = g.get("Opponent") or "Unknown"
        location = g.get("Location", "TBD")

        rows += f"""
        <tr>
            <td style="padding:8px;border:1px solid #ddd;">{date}</td>
            <td style="padding:8px;border:1px solid #ddd;">{time}</td>
            <td style="padding:8px;border:1px solid #ddd;">{opponent}</td>
            <td style="padding:8px;border:1px solid #ddd;">{location}</td>
        </tr>"""

    html = f"""
    <html>
    <body style="font-family:Arial,sans-serif;color:#333;">
        <h2 style="color:#1a3a5c;">⚾ Game Schedule for {player_name}</h2>
        <p>Here are the latest games from Perfect Game:</p>
        <table style="border-collapse:collapse;width:100%;max-width:700px;">
            <thead>
                <tr style="background-color:#1a3a5c;color:white;">
                    <th style="padding:10px;border:1px solid #ddd;">Date</th>
                    <th style="padding:10px;border:1px solid #ddd;">Time</th>
                    <th style="padding:10px;border:1px solid #ddd;">Opponent</th>
                    <th style="padding:10px;border:1px solid #ddd;">Location</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        <br>
        <p style="font-size:12px;color:#888;">
            Powered by Perfect Game Scraper
        </p>
    </body>
    </html>
    """
    return html


def send_email(to_addr, subject, html_body):
    """Send an HTML email via Gmail SMTP."""
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        print("ERROR: EMAIL_ADDRESS and EMAIL_APP_PASSWORD must be set in .env")
        print("  1. Go to https://myaccount.google.com/apppasswords")
        print("  2. Generate an App Password for 'Mail'")
        print("  3. Paste it into .env as EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_addr

    msg.attach(MIMEText(html_body, "html"))

    try:
        print(f"Connecting to Gmail SMTP...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to_addr, msg.as_string())
        print(f"✅ Email sent successfully to {to_addr}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("❌ Authentication failed. Check your EMAIL_APP_PASSWORD in .env")
        print("   Make sure you're using a Google App Password, not your regular password.")
        return False
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Email the game schedule.")
    parser.add_argument(
        "--schedule", type=str, default="team_schedule.json",
        help="Path to the schedule JSON file."
    )
    parser.add_argument(
        "--to", type=str, default=None,
        help="Recipient email (defaults to EMAIL_ADDRESS from .env)."
    )
    parser.add_argument(
        "--upcoming-only", action="store_true",
        help="Only include upcoming games (exclude past results)."
    )
    parser.add_argument(
        "--player", type=str, default="Parker Bowden",
        help="Player name for the email subject."
    )
    args = parser.parse_args()

    to_addr = args.to or EMAIL_ADDRESS
    if not to_addr:
        print("ERROR: No recipient email. Set EMAIL_ADDRESS in .env or use --to.")
        return

    # Load schedule
    try:
        games = load_schedule(args.schedule)
    except FileNotFoundError:
        print(f"ERROR: Schedule file '{args.schedule}' not found.")
        print("Run perfect_game_scraper.py first to generate team_schedule.json")
        return
    except json.JSONDecodeError:
        print(f"ERROR: Failed to parse '{args.schedule}' as JSON.")
        return

    if args.upcoming_only:
        games = filter_upcoming(games)

    if not games:
        print("No games found in the schedule to email.")
        return

    print(f"Found {len(games)} game(s) to include in the email.")

    subject = f"⚾ {args.player} - Game Schedule Update"
    html_body = build_email_body(games, player_name=args.player)

    send_email(to_addr, subject, html_body)


if __name__ == "__main__":
    main()
