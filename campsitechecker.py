import os
import time
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

GMAIL_ADDRESS      = "marleytosh@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
FIDO_NUMBER        = "2508847865" 

ARRIVAL_DATE   = "07/31/2026"
DEPARTURE_DATE = "08/03/2026"
UNIT_TYPE      = "Tent"

URL = (
    "https://properties3.camping.com/descanso-bay-regional-park/"
    "guid-b8173a80-045c-47de-9517-cb038873bc3c/reservations/availability"
)
BOOKING_URL = (
    "https://properties3.camping.com/descanso-bay-regional-park/reservations"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)


def send_email(subject, body_text, body_html):
    recipients = [
        GMAIL_ADDRESS,
        f"{FIDO_NUMBER}@fido.ca",
    ]
    for recipient in recipients:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = recipient
        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, recipient, msg.as_string())
        log.info("Alert sent to %s", recipient)


def send_alert(sites_found):
    subject   = "Campsite Available! Descanso Bay Jul 31 - Aug 3"
    body_text = f"Availability found!\n\nDates: July 31 - Aug 3, 2026\nType: Tent\n\n{sites_found}\n\nBook now: {BOOKING_URL}"
    body_html = f"<h2>Campsite Available at Descanso Bay!</h2><p><strong>Dates:</strong> July 31 - Aug 3, 2026<br><strong>Type:</strong> Tent</p><pre>{sites_found}</pre><p><a href='{BOOKING_URL}'>Book Now</a></p>"
    send_email(subject, body_text, body_html)


def check_availability():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page    = browser.new_page()
        try:
            log.info("Loading reservation page...")
            page.goto(URL, wait_until="networkidle", timeout=60_000)
            time.sleep(3)

            log.info("Looking for date input fields...")
            page.wait_for_selector("input", timeout=15_000)

            inputs = page.locator("input[type='text'], input:not([type])").all()
            log.info("Found %d text inputs", len(inputs))

            filled = 0
            for inp in inputs:
                try:
                    if not inp.is_visible():
                        continue
                    inp.click()
                    time.sleep(0.3)
                    inp.fill("")
                    if filled == 0:
                        inp.type(ARRIVAL_DATE, delay=50)
                        log.info("Typed arrival date into input %d", filled)
                        filled += 1
                    elif filled == 1:
                        inp.type(DEPARTURE_DATE, delay=50)
                        log.info("Typed departure date into input %d", filled)
                        filled += 1
                    if filled == 2:
                        break
                except Exception:
                    continue

            time.sleep(0.5)

            log.info("Looking for unit type dropdown...")
            selects = page.locator("select").all()
            for sel in selects:
                try:
                    options = sel.locator("option").all_text_contents()
                    if "Tent" in options:
                        sel.select_option(label="Tent")
                        log.info("Selected Tent")
                        break
                except Exception:
                    continue

            time.sleep(0.5)

            log.info("Clicking search button...")
            for selector in [
                "input[value*='START']",
                "input[type='submit']",
                "button[type='submit']",
                "button:has-text('Search')",
            ]:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible():
                        btn.click()
                        log.info("Clicked: %s", selector)
                        break
                except Exception:
                    continue

            log.info("Waiting for results...")
            page.wait_for_load_state("networkidle", timeout=30_000)
            time.sleep(4)

            content = page.content().lower()
            body    = page.inner_text("body")

            negative = ["no sites available", "no campsites", "0 sites", "not available", "sold out"]
            for sig in negative:
                if sig in content:
                    log.info("No availability (matched: '%s')", sig)
                    browser.close()
                    return None

            positive = ["available", "select site", "add to cart"]
            found    = [s for s in positive if s in content]
            if found:
                lines   = [l.strip() for l in body.splitlines() if any(k in l.lower() for k in ["site", "available", "tent"]) and l.strip()]
                summary = "\n".join(lines[:20]) or "(See booking page)"
                log.info("Availability found!")
                browser.close()
                return summary

            log.info("Could not determine availability -- treating as unavailable")
            browser.close()
            return None

        except PlaywrightTimeout as e:
            log.error("Timeout: %s", e)
            browser.close()
            return None
        except Exception as e:
            log.error("Error: %s", e)
            browser.close()
            return None


def main():
    log.info("Campsite Checker running -- single check")
    result = check_availability()
    if result:
        log.info("Availability found -- sending alerts")
        send_alert(result)
    else:
        log.info("No availability this check.")


if __name__ == "__main__":
    main()
