import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import time
import re

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

MYT = pytz.timezone("Asia/Kuala_Lumpur")
EST = pytz.timezone("America/New_York")

IMPACT_EMOJI = {
    "high":   "🔴",
    "medium": "🟠",
    "low":    "🟡",
    "none":   "⚪",
}


def convert_to_myt(time_str, date_myt):
    """
    Convert ForexFactory time string (EST/EDT) to MYT.
    time_str examples: '8:30am', '2:00pm', 'All Day', 'Tentative'
    date_myt: the current date in MYT (datetime object)
    """
    if not time_str or time_str in ("—", "All Day", "Tentative", ""):
        return time_str or "—"

    # Parse the time string
    time_str_clean = time_str.strip().lower()
    match = re.match(r"(\d{1,2}):(\d{2})(am|pm)", time_str_clean)
    if not match:
        return time_str  # Can't parse, return as-is

    hour = int(match.group(1))
    minute = int(match.group(2))
    ampm = match.group(3)

    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    # ForexFactory shows the PREVIOUS day's evening events for the next day
    # e.g. "9:00pm" on Monday's calendar = 9pm EST Monday
    # Build the EST datetime using the MYT date as base
    # MYT is UTC+8, EST is UTC-5 (EDT is UTC-4)
    # When it's 7am MYT on Tuesday, it's still Monday evening in EST
    # So we use the MYT date minus 1 day for overnight EST times
    try:
        # Try same day first in EST
        est_dt = EST.localize(datetime(
            date_myt.year, date_myt.month, date_myt.day,
            hour, minute, 0
        ))
        myt_dt = est_dt.astimezone(MYT)
        return myt_dt.strftime("%-I:%M%p").lower().replace("am", "am").replace("pm", "pm").upper()
    except Exception:
        return time_str


def scrape_forexfactory():
    """Scrape today's USD events from ForexFactory."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    })

    # Visit homepage first to grab cookies
    try:
        session.get("https://www.forexfactory.com/", timeout=15)
        time.sleep(2)
    except Exception as e:
        print(f"Homepage visit warning: {e}")

    now_myt = datetime.now(MYT)
    date_str = now_myt.strftime("%b%d.%Y").lower()
    url = f"https://www.forexfactory.com/calendar?day={date_str}"
    print(f"Fetching: {url}")

    response = session.get(url, timeout=15)
    print(f"HTTP status: {response.status_code}")
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")

    rows = (
        soup.select("tr.calendar__row--grey, tr.calendar__row")
        or soup.select("tr[class*='calendar__row']")
        or soup.select("table.calendar tr")
    )
    print(f"Total rows found: {len(rows)}")

    events = []
    current_time_raw = None

    for row in rows:
        # Time (carried forward across merged rows)
        for sel in ["td.calendar__time", "td[class*='calendar__time']"]:
            time_cell = row.select_one(sel)
            if time_cell:
                raw = time_cell.get_text(strip=True)
                if raw and raw.lower() not in ("", "all day", "tentative", "data"):
                    current_time_raw = raw
                break

        # Currency
        currency = ""
        for sel in ["td.calendar__currency", "td[class*='calendar__currency']"]:
            el = row.select_one(sel)
            if el:
                currency = el.get_text(strip=True)
                break
        if currency != "USD":
            continue

        # Impact
        impact = "none"
        for sel in ["td.calendar__impact span", "td[class*='impact'] span"]:
            span = row.select_one(sel)
            if span:
                cls_str = " ".join(span.get("class", []))
                if "red" in cls_str or "high" in cls_str:
                    impact = "high"
                elif "ora" in cls_str or "medium" in cls_str or "orange" in cls_str:
                    impact = "medium"
                elif "yel" in cls_str or "low" in cls_str or "yellow" in cls_str:
                    impact = "low"
                break

        # Event name
        event_name = ""
        for sel in [
            "td.calendar__event span.calendar__event-title",
            "td[class*='event'] span[class*='title']",
            "td.calendar__event",
            "td[class*='event']",
        ]:
            el = row.select_one(sel)
            if el:
                event_name = el.get_text(strip=True)
                break
        if not event_name:
            continue

        def cell_text(selectors):
            for s in selectors:
                el = row.select_one(s)
                if el:
                    return el.get_text(strip=True)
            return ""

        # Convert EST time to MYT
        myt_time = convert_to_myt(current_time_raw, now_myt)

        events.append({
            "time":     myt_time,
            "impact":   impact,
            "event":    event_name,
            "forecast": cell_text(["td.calendar__forecast", "td[class*='forecast']"]),
            "previous": cell_text(["td.calendar__previous", "td[class*='previous']"]),
            "actual":   cell_text(["td.calendar__actual",   "td[class*='actual']"]),
        })

    return events


def format_message(events):
    now_myt = datetime.now(MYT)
    date_str = now_myt.strftime("%A, %d %B %Y")

    if not events:
        return (
            f"📅 *USD Economic Calendar*\n"
            f"_{date_str}_\n\n"
            f"✅ No USD events today\. Clean slate\! 🧘"
        )

    lines = [
        f"📅 *USD Economic Calendar*",
        f"_{date_str}_",
        f"🇲🇾 _All times in Malaysia Time \(MYT\)_",
        f"",
    ]

    for e in events:
        emoji = IMPACT_EMOJI.get(e["impact"], "⚪")
        # Escape special MarkdownV2 chars in event name
        safe_name = (e["event"]
            .replace("-", "\\-").replace(".", "\\.").replace("(", "\\(")
            .replace(")", "\\)").replace("!", "\\!").replace(">", "\\>"))

        lines.append(f"🕐 `{e['time']}`  {emoji}")
        lines.append(f"*{safe_name}*")

        details = []
        if e["forecast"]:
            details.append(f"Fcst: `{e['forecast']}`")
        if e["previous"]:
            details.append(f"Prev: `{e['previous']}`")
        if details:
            lines.append("  ".join(details))
        lines.append("——————————————")

    lines.append("_Source: ForexFactory\\.com_")
    return "\n".join(lines)


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":                  TELEGRAM_CHAT_ID,
        "text":                     message,
        "parse_mode":               "MarkdownV2",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=10)
    if not r.ok:
        print(f"Telegram error body: {r.text}")
    r.raise_for_status()
    print(f"✅ Sent! Status: {r.status_code}")


def main():
    print("📡 Scraping ForexFactory for today's USD events...")
    events = scrape_forexfactory()
    print(f"Found {len(events)} USD events.")

    message = format_message(events)
    print("\n--- Message Preview ---")
    print(message)
    print("--- End Preview ---\n")

    print("📨 Sending to Telegram...")
    send_telegram(message)


if __name__ == "__main__":
    main()
