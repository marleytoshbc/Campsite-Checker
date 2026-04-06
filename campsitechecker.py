"""
Descanso Bay Campsite Availability Checker
Fetches the map iframe page and parses the hidden MapDataID table.
IconType 1 = green (available), 2 = yellow (alternate), 3 = red (not available)
Sends email via Gmail and push notification via ntfy.sh
"""

import os
import re
import smtplib
import logging
import urllib.request
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
GMAIL_ADDRESS      = "marleytosh@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
NTFY_TOPIC         = "DescansoBayAlerts2026"

ARRIVAL_DATE   = "08/04/2026"
DEPARTURE_DATE = "08/07/2026"

# Descanso Bay constants (from page source)
CUSTOMER_ID = "56537"
GUID        = "e21798cd-02b6-4388-9d32-8ac6d75e8aa5"
AREA_ID     = "300000011"
MAP_ID      = "300000020"
SPACE_TYPE  = "21"
UNIT_TYPE   = "5"
ICON_NAME   = "pen_med"

BASE_URL    = "https://properties3.camping.com"
BOOKING_URL = "https://properties3.camping.com/descanso-bay-regional-park/reservations"
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)


def build_map_url():
    params = urllib.parse.urlencode({
        "ModuleTypeID": "1009",
        "CustomerID":   CUSTOMER_ID,
        "FromDate":     ARRIVAL_DATE,
        "ToDate":       DEPARTURE_DATE,
        "AmpService":   "",
        "UnitType":     UNIT_TYPE,
        "Width":        "-1",
        "Length":       "-1",
        "SideOuts":     "-1",
        "UomID":        "1",
        "SpaceClass":   "-1",
        "Duration":     "",
        "StartTime":    "",
        "SpaceType":    SPACE_TYPE,
        "MapID":        MAP_ID,
        "IconName":     ICON_NAME,
        "Location":     "-1",
        "Avalability":  "-1",
        "Handicap":     "-1",
        "Height":       "-1",
        "Depth":        "-1",
        "Online":       "1",
        "AreaID":       AREA_ID,
        "TowVehicleLengthID": "-1",
    })
    return (
        f"{BASE_URL}/online/map/Customer_Setup_Facility_Map.aspx?{params}"
    )


def fetch_map_page(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": (
            f"{BASE_URL}/descanso-bay-regional-park/guid-{GUID}"
            f"/reservations/availability"
        ),
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_availability(html):
    """
    Parse the hidden MapDataID table.
    Columns: SpaceID | SiteNum | Coords | SpaceType | SpaceClass | SpaceAttr | ThumbPhoto | IconType | ...
    IconType 1 = available (green), 2 = alternate (yellow), 3 = not available (red)
    """
    available = []

    match = re.search(
        r'<table[^>]*id=[\'"]MapDataID[\'"][^>]*>(.*?)</table>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        log.warning("MapDataID table not found in response")
        return available

    table_html = match.group(1)
    rows = re.findall(r'<tr>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
    log.info("Found %d site rows in map table", len(rows))

    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 8:
            continue

        site_num   = cells[1].strip()
        space_type = cells[3].strip()
        space_cls  = cells[4].strip()
        icon_type  = cells[7].strip()

        log.info("Site %s | %s | %s | IconType=%s", site_num, space_type, space_cls, icon_type)

        if icon_type == "1":
            available.append(f"Site {site_num} -- {space_type} / {space_cls} (Available)")
        elif icon_type == "2":
            available.append(f"Site {site_num} -- {space_type} / {space_cls} (Alternate Availability)")

    return available


def send_email(available_sites):
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
        f"<p><strong>Dates:</strong> July 31 - Aug 3, 2026<br>"
        f"<strong>Type:</strong> Tent</p>"
        f"<pre>{site_list}</pre>"
        f"<p><a href='{BOOKING_URL}' style='font-size:18px;font-weight:bold;'>"
        f"Book Now</a></p>"
    )

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = GMAIL_ADDRESS
        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, msg.as_string())
        log.info("Email alert sent to %s", GMAIL_ADDRESS)
    except Exception as e:
        log.error("Failed to send email: %s", e)


def send_ntfy(available_sites):
    site_list = "\n".join(available_sites)
    message   = f"Sites open:\n{site_list}\n\nBook now: {BOOKING_URL}"
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            method="POST",
            headers={
                "Title":    "Campsite Available! Descanso Bay Jul 31-Aug 3",
                "Priority": "urgent",
                "Tags":     "camping,tent",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info("ntfy notification sent: %s", resp.status)
    except Exception as e:
        log.error("ntfy failed: %s", e)


def main():
    log.info("Campsite Checker -- single run")
    log.info("Dates: %s to %s | Tent | Descanso Bay", ARRIVAL_DATE, DEPARTURE_DATE)

    url = build_map_url()
    log.info("Fetching map page...")

    try:
        html = fetch_map_page(url)
    except Exception as e:
        log.error("Failed to fetch map page: %s", e)
        return

    available = parse_availability(html)

    if available:
        log.info("*** AVAILABILITY FOUND: %d site(s) ***", len(available))
        for s in available:
            log.info("  -> %s", s)
        send_email(available)
        send_ntfy(available)
    else:
        log.info("No availability this check.")


if __name__ == "__main__":
    main()
