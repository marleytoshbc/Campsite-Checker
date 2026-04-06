"""
Descanso Bay Campsite Availability Checker
Calls the camping.com WebService API directly to check for Tent site availability.
Sends email + Fido SMS alert when a site is found.

Jul 31 - Aug 3, 2026 | Tent | Descanso Bay Regional Park
"""

import os
import time
import json
import logging
import smtplib
import urllib.request
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from xml.etree import ElementTree

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
GMAIL_ADDRESS      = "marleytosh@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
FIDO_NUMBER        = "2508847865"   # <-- replace with your 10-digit Fido number

ARRIVAL_DATE   = "08/04/2026"   # MM/DD/YYYY
DEPARTURE_DATE = "08/07/2026"   # MM/DD/YYYY

# Descanso Bay site constants (extracted from page source)
CUSTOMER_ID      = "56537"
GUID             = "e21798cd-02b6-4388-9d32-8ac6d75e8aa5"
AREA_ID          = "300000011"
MAP_ID           = "300000020"
SPACE_TYPE_ID    = "21"          # Tent = unit type 5, space type 21
UNIT_TYPE_ID     = "5"           # Tent
ORDER_SOURCE     = "10"
ICON_NAME        = "pen_med"

BASE_URL = "https://properties3.camping.com"
BOOKING_URL = "https://properties3.camping.com/descanso-bay-regional-park/reservations"
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)


def build_api_url():
    """Build the WebService URL that returns availability data."""
    params = {
        "ActionType": "1005",
        "CustomerID": CUSTOMER_ID,
        "FromDate": ARRIVAL_DATE,
        "ToDate": DEPARTURE_DATE,
        "AmpService": "",
        "UnitType": UNIT_TYPE_ID,
        "Width": "-1",
        "Length": "-1",
        "SideOuts": "-1",
        "UomID": "1",
        "SpaceClass": "-1",
        "Duration": "",
        "StartTime": "",
        "SpaceType": SPACE_TYPE_ID,
        "MapID": MAP_ID,
        "IconName": ICON_NAME,
        "Location": "-1",
        "Avalability": "-1",
        "Handicap": "-1",
        "Height": "-1",
        "Depth": "-1",
        "Online": "1",
        "AreaID": AREA_ID,
        "TowVehicleLengthID": "-1",
        "GUID": GUID,
        "e": str(time.time()),
    }
    query = urllib.parse.urlencode(params)
    return f"{BASE_URL}/descanso-bay-regional-park/WebService.ashx?{query}"


def check_availability():
    """
    Calls the WebService API and checks for available sites.
    Returns a list of available site descriptions, or empty list if none.
    """
    url = build_api_url()
    log.info("Calling availability API...")
    log.debug("URL: %s", url)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/javascript, */*",
        "Referer": f"{BASE_URL}/descanso-bay-regional-park/reservations/availability",
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except Exception as e:
        log.error("API request failed: %s", e)
        return []

    log.debug("Raw response (first 500 chars): %s", raw[:500])

    # The API returns XML. Parse it.
    # Available sites have IsSelect="1", unavailable have IsSelect="0"
    available_sites = []

    try:
        # Try JSON first (some responses come back as JSON)
        data = json.loads(raw)
        log.info("Response is JSON: %s", str(data)[:200])
        # If JSON, check for available sites in whatever structure comes back
        text = json.dumps(data).lower()
        if "available" in text and "isselect" in text:
            available_sites.append("Site available (see booking page for details)")
        return available_sites

    except (json.JSONDecodeError, ValueError):
        pass

    # Try XML parsing
    try:
        root = ElementTree.fromstring(raw)

        # Look for rowhead rows -- these are the actual campsites
        # IsSelect="1" means available for your dates
        # IsSelect="0" means not available
        rowhead = root.find(".//rowhead")
        if rowhead is None:
            log.info("No rowhead element found in XML -- no sites returned")
            return []

        rows = rowhead.findall("row")
        log.info("Found %d site rows in response", len(rows))

        for row in rows:
            is_select = row.get("IsSelect", "0")
            site_desc = row.text or row.get("id", "Unknown site")
            site_id   = row.get("id", "?")

            if is_select == "1":
                log.info("AVAILABLE site found: ID=%s Desc=%s", site_id, site_desc)
                available_sites.append(f"Site {site_id}: {site_desc}")
            else:
                log.info("Not available: ID=%s", site_id)

        return available_sites

    except ElementTree.ParseError as e:
        log.warning("XML parse failed: %s", e)
        log.info("Raw response: %s", raw[:1000])

        # Last resort: look for IsSelect="1" as plain text
        if 'IsSelect="1"' in raw or "isselect=1" in raw.lower():
            log.info("Found IsSelect=1 via text search -- availability detected")
            return ["Site available (see booking page for details)"]

        return []


def send_alerts(available_sites):
    """Send email to Gmail and SMS via Fido email-to-text."""
    site_list = "\n".join(available_sites)
    subject   = "Campsite Available! Descanso Bay Jul 31 - Aug 3"
    body_text = (
        f"Availability found at Descanso Bay!\n\n"
        f"Dates: July 31 - Aug 3, 2026\n"
        f"Type: Tent\n\n"
        f"Sites:\n{site_list}\n\n"
        f"Book now: {BOOKING_URL}"
    )
    body_html = (
        f"<h2>Campsite Available at Descanso Bay!</h2>"
        f"<p><strong>Dates:</strong> July 31 – Aug 3, 2026<br>"
        f"<strong>Type:</strong> Tent</p>"
        f"<pre>{site_list}</pre>"
        f"<p><a href='{BOOKING_URL}' style='font-size:18px;font-weight:bold;'>"
        f"👉 Book Now</a></p>"
    )

    recipients = [GMAIL_ADDRESS, f"{FIDO_NUMBER}@fido.ca"]

    for recipient in recipients:
        try:
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
        except Exception as e:
            log.error("Failed to send to %s: %s", recipient, e)


def main():
    log.info("Campsite Checker -- single run")
    log.info("Dates: %s to %s | Tent | Descanso Bay", ARRIVAL_DATE, DEPARTURE_DATE)

    available = check_availability()

    if available:
        log.info("*** AVAILABILITY FOUND: %s site(s) ***", len(available))
        for s in available:
            log.info("  -> %s", s)
        send_alerts(available)
    else:
        log.info("No availability this check.")


if __name__ == "__main__":
    main()
