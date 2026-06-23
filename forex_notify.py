import os
import requests
from datetime import datetime
import pytz

# ===== Telegram =====

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ===== Timezone =====

MYT = pytz.timezone("Asia/Kuala_Lumpur")
UTC = pytz.utc

# ===== Impact Emoji =====

IMPACT_EMOJI = {
"high": "🔴",
"medium": "🟠",
"low": "🟡"
}

def get_usd_events():
url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

```
headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

response = requests.get(url, headers=headers, timeout=20)
response.raise_for_status()

data = response.json()

today_myt = datetime.now(MYT).strftime("%Y-%m-%d")

events = []

for item in data:

    country = str(item.get("Country", "")).upper()

    if country != "USD":
        continue

    impact = str(item.get("Impact", "")).lower()

    # Only Medium and High impact news
    if impact not in ["high", "medium"]:
        continue

    date_str = item.get("Date")

    if not date_str:
        continue

    try:
        utc_dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
        utc_dt = UTC.localize(utc_dt)

        myt_dt = utc_dt.astimezone(MYT)

        if myt_dt.strftime("%Y-%m-%d") != today_myt:
            continue

        events.append({
            "time": myt_dt.strftime("%I:%M %p"),
            "impact": impact,
            "title": item.get("Title", ""),
            "forecast": item.get("Forecast", ""),
            "previous": item.get("Previous", ""),
            "actual": item.get("Actual", "")
        })

    except Exception as e:
        print("Skip event:", e)

events.sort(key=lambda x: datetime.strptime(x["time"], "%I:%M %p"))

return events
```

def format_message(events):

```
today = datetime.now(MYT).strftime("%A, %d %B %Y")

if len(events) == 0:
    return (
        f"📅 USD Economic Calendar\n"
        f"{today}\n\n"
        f"✅ No medium/high USD events today."
    )

message = (
    f"📅 USD Economic Calendar\n"
    f"{today}\n"
    f"🇲🇾 Malaysia Time\n\n"
)

for e in events:

    emoji = IMPACT_EMOJI.get(e["impact"], "⚪")

    message += (
        f"{emoji} {e['time']}\n"
        f"{e['title']}\n"
    )

    if e["forecast"]:
        message += f"Forecast: {e['forecast']}\n"

    if e["previous"]:
        message += f"Previous: {e['previous']}\n"

    if e["actual"]:
        message += f"Actual: {e['actual']}\n"

    message += "────────────────\n"

return message
```

def send_telegram(message):

```
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

payload = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": message
}

response = requests.post(url, json=payload, timeout=15)

response.raise_for_status()

print("✅ Telegram message sent")
```

def main():

```
print("Fetching ForexFactory events...")

events = get_usd_events()

print(f"Found {len(events)} events")

message = format_message(events)

print(message)

send_telegram(message)
```

if **name** == "**main**":
main()
