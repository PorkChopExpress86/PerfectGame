"""
test_email.py - Sends a quick test email to verify SMTP credentials work.

Usage:
    python3 test_email.py
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")


def test_email():
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        print("❌ EMAIL_ADDRESS and EMAIL_APP_PASSWORD must be set in .env")
        return False

    if EMAIL_APP_PASSWORD == "your_app_password_here":
        print("❌ You haven't set your App Password yet!")
        print("   1. Go to https://myaccount.google.com/apppasswords")
        print("   2. Generate an App Password for 'Mail'")
        print("   3. Replace 'your_app_password_here' in .env")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "✅ PerfectGame Scraper - Email Test"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_ADDRESS

    html = """
    <html>
    <body style="font-family:Arial,sans-serif;color:#333;">
        <h2 style="color:#1a3a5c;">✅ Email Test Successful!</h2>
        <p>Your PerfectGame schedule email is configured correctly.</p>
        <p>You will receive game schedule updates at this address.</p>
        <hr>
        <p style="font-size:12px;color:#888;">
            Powered by Perfect Game Scraper
        </p>
    </body>
    </html>
    """
    msg.attach(MIMEText(html, "html"))

    try:
        print(f"Testing SMTP connection to smtp.gmail.com:465...")
        print(f"  From: {EMAIL_ADDRESS}")
        print(f"  To:   {EMAIL_ADDRESS}")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, EMAIL_ADDRESS, msg.as_string())
        print("✅ Test email sent successfully! Check your inbox.")
        return True
    except smtplib.SMTPAuthenticationError:
        print("❌ Authentication failed.")
        print("   Make sure EMAIL_APP_PASSWORD in .env is a Google App Password,")
        print("   NOT your regular Gmail password.")
        return False
    except TimeoutError:
        print("❌ Connection timed out. Check your network / firewall.")
        return False
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


if __name__ == "__main__":
    test_email()
