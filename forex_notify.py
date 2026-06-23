```python
import os
import requests
from datetime import datetime
import pytz

# ===== Telegram =====
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ===== Timezones =====
MYT = pytz.timezone("Asia/Kuala_Lumpur")
UTC = pytz.utc

# ===== Impact Emoji =====
IMPACT_EMOJI = {
    "High": "🔴",
    "Medium": "🟠",
    "Low": "🟡"
}


def get_usd_events():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()

    data = response.json()

    now_myt = datetime.now(MYT)
    today_str = now_myt.strftime("%Y-%m-%d")

    usd_events = []

    for event in data:

        if event.get("Country") != "USD":
            continue

        date_utc = event.get("Date")

        if not date_utc:
            continue

        try:
            utc_dt = datetime.strptime(date_utc, "%Y-%m-%dT%H:%M:%S")
            utc_dt = UTC.localize(utc_dt)
            myt_dt = utc_dt.astimezone(MYT)

            if myt_dt.strftime("%Y-%m-%d") != today_str:
                continue

            usd_events.append({
                "time": myt_dt.strftime("%I:%M %p"),
                "impact": event.get("Impact", ""),
                "title": event.get("Title", ""),
                "actual": event.get("Actual", ""),
                "forecast": event.get("Forecast", ""),
                "previous": event.get("Previous", "")
            })

        except Exception as e:
            print(e)

    usd_events.sort(key=lambda x: x["time"])

    return usd_events


def format_message(events):

    today = datetime.now(MYT).strftime("%A, %d %B %Y")

    if len(events) == 0:
        return (
            f"📅 USD Economic Calendar\n"
            f"{today}\n\n"
            f"✅ No USD events today"
        )

    msg = (
        f"📅 USD Economic Calendar\n"
        f"{today}\n"
        f"🇲🇾 Malaysia Time (MYT)\n\n"
    )

    for e in events:

        emoji = IMPACT_EMOJI.get(e["impact"], "⚪")

        msg += (
            f"🕐 {e['time']} {emoji}\n"
            f"{e['title']}\n"
        )

        if e["forecast"]:
            msg += f"Forecast: {e['forecast']}\n"

        if e["previous"]:
            msg += f"Previous: {e['previous']}\n"

        if e["actual"]:
            msg += f"Actual: {e['actual']}\n"

        msg += "——————————\n"

    msg += "\nSource: ForexFactory"

    return msg


def send_telegram(message):

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()

    print("✅ Telegram message sent")


def main():

    print("Fetching USD events...")

    events = get_usd_events()

    print("Found", len(events), "USD events")

    message = format_message(events)

    print(message)

    send_telegram(message)


if __name__ == "__main__":
    main()
```
