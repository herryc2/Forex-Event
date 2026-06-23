import os
import requests

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def get_usd_events():

```
url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

response = requests.get(
    url,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=20
)

response.raise_for_status()

data = response.json()

events = []

for event in data:

    if str(event.get("Country", "")).upper() != "USD":
        continue

    impact = str(event.get("Impact", "")).lower()

    if impact not in ["high", "medium"]:
        continue

    events.append({
        "title": event.get("Title", ""),
        "impact": impact
    })

return events
```

def send_telegram(message):

```
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

payload = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": message
}

response = requests.post(url, json=payload)

response.raise_for_status()
```

def main():

```
print("Fetching events...")

events = get_usd_events()

print(events)

if len(events) == 0:
    message = "No medium/high USD events found."
else:

    message = "USD Events:\n\n"

    for e in events:
        emoji = "🔴" if e["impact"] == "high" else "🟠"
        message += f"{emoji} {e['title']}\n"

send_telegram(message)

print("Done")
```

if **name** == "**main**":
main()
