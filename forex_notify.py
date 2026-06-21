import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import time

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

MYT = pytz.timezone("Asia/Kuala_Lumpur")

IMPACT_EMOJI = {
    "red":  "🔴",
    "ora":  "🟠",
    "yel":  "🟡",
    "gra":  "⚪",
}

IMPACT_LABEL = {
    "red":  "High",
    "ora":  "Medium",
    "yel":  "Low",
    "gra":  "Non-Economic",
}


def get_session():
    """Create a session that mimics a real browser visiting ForexFactory."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    # Visit homepage first to get cookies (mimics real browser)
    try:
        session.get("https://www.forexfactory.com/", timeout=15)
        time.sleep(2)
    except Exception:
        pass
    return session


def scrape_forexfactory():
    """Scrape today's USD events from ForexFactory."""
    session = get_session()

    now_myt = datetime.now(MYT)
    # FF uses format like: jun22.2026
    date_str = now_myt.strftime("%b%d.%Y").lower()
    url = f"https://www.forexfactory.com/calendar?day={date_str}"

    response = session.get(url, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.select("tr.calendar__row")

    events = []
    current_time = None

    for row in rows:
        # ForexFactory reuses time cell across grouped rows — carry it forward
        time_cell = row.select_one("td.calendar__time")
        if time_cell:
            raw_time = time_cell.get_text(strip=True)
            if raw_time and raw_time.lower() not in ("", "all day", "tentative"):
                current_time = raw_time

        currency_cell = row.select_one("td.calendar__currency")
        if not currency_cell:
            continue
        currency = currency_cell.get_text(strip=True)
        if currency != "USD":
            continue

        # Impact colour class
        impact_class = ""
        impact_span = row.select_one("td.calendar__impact span")
        if impact_span:
            for cls in impact_span.get("class", []):
                for key in IMPACT_EMOJI:
                    if key in cls:
                        impact_class = key
                        break

        # Event name
        name_el = row.select_one("td.calendar__event span.calendar__event-title")
        if not name_el:
            name_el = row.select_one("td.calendar__event")
        event_name = name_el.get_text(strip=True) if name_el else "Unknown Event"

        def cell_text(selector):
            el = row.select_one(selector)
            return el.get_text(strip=True) if el else ""

        events.append({
            "time":     current_time or "—",
            "impact":   impact_class,
            "event":    event_name,
            "forecast": cell_text("td.calendar__forecast"),
            "previous": cell_text("td.calendar__previous"),
            "actual":   cell_text("td.calendar__actual"),
        })

    return events


def format_message(events):
    """Format events into a clean Telegram message."""
    now_myt = datetime.now(MYT)
    date_str = now_myt.strftime("%A, %d %B %Y")

    header = (
        f"📅 *USD Economic Calendar*\n"
        f"_{date_str} — Malaysia Time (MYT)_\n"
    )

    if not events:
        return header + "\n✅ No USD events scheduled today. Clean slate! 🧘"

    lines = [header, "```"]

    for e in events:
        emoji  = IMPACT_EMOJI.get(e["impact"], "⚪")
        label  = IMPACT_LABEL.get(e["impact"], "N/A")
        time_s = e["time"].rjust(8)

        lines.append(f"{time_s}  {emoji} {label}")
        lines.append(f"  ➤ {e['event']}")

        details = []
        if e["forecast"]:
            details.append(f"Fcst: {e['forecast']}")
        if e["previous"]:
            details.append(f"Prev: {e['previous']}")
        if details:
            lines.append(f"  {'  |  '.join(details)}")
        lines.append("")

    lines.append("```")
    lines.append("_Source: ForexFactory.com_")

    return "\n".join(lines)


def send_telegram(message):
    """Send message to Telegram channel."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":                  TELEGRAM_CHAT_ID,
        "text":                     message,
        "parse_mode":               "Markdown",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
    print(f"✅ Sent! Status: {r.status_code}")


def main():
    print("📡 Scraping ForexFactory for today's USD events...")
    events = scrape_forexfactory()
    print(f"   Found {len(events)} USD events.")

    message = format_message(events)
    print("\n--- Preview ---")
    print(message)
    print("--- End Preview ---\n")

    print("📨 Sending to Telegram...")
    send_telegram(message)


if __name__ == "__main__":
    main()
