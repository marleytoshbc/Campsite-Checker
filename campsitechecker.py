"""
Descanso Bay Campsite Availability Checker
Checks for Tent availability July 31 - Aug 3, 2026 and sends Gmail alert.
"""

import time
import smtplib
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ─────────────────────────────────────────────
# CONFIGURATION -- edit these values
# ─────────────────────────────────────────────
GMAIL_ADDRESS   = "marleytosh@gmail.com"   # sends AND receives the alert
import os
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

ARRIVAL_DATE    = "07/31/2026"
DEPARTURE_DATE  = "08/03/2026"
UNIT_TYPE       = "Tent"
CHECK_INTERVAL  = 3600   # seconds between checks (3600 = 1 hour)

URL = (
    "https://properties3.camping.com/descanso-bay-regional-park/"
    "guid-b8173a80-045c-47de-9517-cb038873bb3c/reservations/availability"
)

BOOKING_URL = (
    "https://properties3.camping.com/descanso-bay-regional-park/reservations"
)
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("campsite_checker.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def send_alert(sites_found: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🏕️ Campsite Available! Descanso Bay Jul 31 - Aug 3"
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = GMAIL_ADDRESS

    body_text = f"""
Availability found at Descanso Bay Regional Park!

Dates:  July 31 - August 3, 2026  (3 nights)
Type:   Tent

Sites found:
{sites_found}

Book now before it's gone:
{BOOKING_URL}

-- Campsite Checker Bot
"""
    body_html = f"""
<html><body>
<h2>🏕️ Campsite Available at Descanso Bay!</h2>
<p><strong>Dates:</strong> July 31 – August 3, 2026 (3 nights)<br>
<strong>Type:</strong> Tent</p>
<h3>Sites found:</h3>
<pre>{sites_found}</pre>
<p><a href="{BOOKING_URL}" style="font-size:16px;font-weight:bold;">
👉 Book Now</a></p>
<p style="color:#888;font-size:12px;">— Campsite Checker Bot</p>
</body></html>
"""
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, msg.as_string())

    log.info("Alert email sent to %s", GMAIL_ADDRESS)


def check_availability() -> str | None:
    """
    Returns a string describing available sites if any are found,
    or None if nothing is available.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            log.info("Loading reservation page...")
            page.goto(URL, wait_until="networkidle", timeout=60_000)

            # ── Arrival date ──
            log.info("Entering arrival date: %s", ARRIVAL_DATE)
            arrival_input = page.locator("input[name*='ArrivalDate'], input[id*='ArrivalDate'], input[placeholder*='Arrival']").first
            arrival_input.wait_for(state="visible", timeout=15_000)
            arrival_input.fill(ARRIVAL_DATE)
            page.keyboard.press("Tab")
            time.sleep(0.5)

            # ── Departure date ──
            log.info("Entering departure date: %s", DEPARTURE_DATE)
            departure_input = page.locator("input[name*='DepartureDate'], input[id*='DepartureDate'], input[placeholder*='Departure']").first
            departure_input.fill(DEPARTURE_DATE)
            page.keyboard.press("Tab")
            time.sleep(0.5)

            # ── Unit type dropdown ──
            log.info("Selecting unit type: %s", UNIT_TYPE)
            unit_select = page.locator("select").filter(has_text="Tent").first
            # Fallback: find any select and pick Tent option
            selects = page.locator("select").all()
            for sel in selects:
                options = sel.locator("option").all_text_contents()
                if "Tent" in options:
                    sel.select_option(label="Tent")
                    log.info("Unit type set to Tent")
                    break
            time.sleep(0.5)

            # ── Click START SEARCH ──
            log.info("Clicking START SEARCH...")
            search_btn = page.locator(
                "input[value*='START SEARCH'], button:has-text('START SEARCH'), input[type='submit']"
            ).first
            search_btn.click()

            # ── Wait for results ──
            log.info("Waiting for results...")
            page.wait_for_load_state("networkidle", timeout=30_000)
            time.sleep(3)

            content = page.content().lower()

            # Check for "not available" or similar negative signals
            negative_signals = [
                "no sites available",
                "no campsites available",
                "no availability",
                "0 sites",
                "not available",
                "sold out",
            ]
            for signal in negative_signals:
                if signal in content:
                    log.info("No availability detected (matched: '%s')", signal)
                    browser.close()
                    return None

            # Check for positive availability signals
            positive_signals = [
                "available",
                "select site",
                "site #",
                "site number",
                "add to cart",
            ]
            found = [s for s in positive_signals if s in content]
            if found:
                # Try to extract site info from the page text
                body_text = page.inner_text("body")
                # Grab a relevant snippet around availability mentions
                lines = [
                    line.strip() for line in body_text.splitlines()
                    if any(kw in line.lower() for kw in ["site", "available", "tent"])
                    and line.strip()
                ]
                summary = "\n".join(lines[:30]) if lines else "(See booking page for details)"
                log.info("Availability found! Signals: %s", found)
                browser.close()
                return summary

            log.info("Could not determine availability clearly -- treating as unavailable.")
            browser.close()
            return None

        except PlaywrightTimeout as e:
            log.error("Timeout during check: %s", e)
            browser.close()
            return None
        except Exception as e:
            log.error("Unexpected error during check: %s", e)
            browser.close()
            return None


def main():
    log.info("=" * 60)
    log.info("Campsite Checker started")
    log.info("Target: Descanso Bay | %s to %s | %s", ARRIVAL_DATE, DEPARTURE_DATE, UNIT_TYPE)
    log.info("Checking every %d minutes", CHECK_INTERVAL // 60)
    log.info("=" * 60)

    alert_sent = False

    while True:
        log.info("--- Running check ---")
        result = check_availability()

        if result:
            log.info("AVAILABILITY FOUND -- sending alert email")
            try:
                send_alert(result)
                alert_sent = True
            except Exception as e:
                log.error("Failed to send email: %s", e)

            # Keep checking every hour even after alert
            # (in case you want to know about more openings)
            log.info("Will check again in %d minutes", CHECK_INTERVAL // 60)
        else:
            log.info("No availability. Next check in %d minutes.", CHECK_INTERVAL // 60)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
