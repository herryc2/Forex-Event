import hashlib
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    MYT = ZoneInfo("Asia/Kuala_Lumpur")
except Exception:
    MYT = timezone(timedelta(hours=8))

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
RUN_MODE = os.getenv("RUN_MODE", "scheduled").strip().lower()
CURRENCIES = [x.strip().upper() for x in os.getenv("CURRENCIES", "USD").split(",") if x.strip()]
IMPACTS = [x.strip().lower() for x in os.getenv("IMPACT_LEVELS", "high,medium").split(",") if x.strip()]

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
STATE_FILE = ".bot_state.json"
USER_AGENT = "Mozilla/5.0 (compatible; ForexEventBot/2.0)"
MAX_MESSAGE_LENGTH = 4000

IMPACT_EMOJI = {"high": "🔴", "medium": "🟠", "low": "🟡", "none": "⚪"}
PAIR_MAP = {
    "USD": "XAU/USD · EUR/USD · GBP/USD · USD/JPY",
    "EUR": "EUR/USD · EUR/GBP · EUR/JPY",
    "GBP": "GBP/USD · EUR/GBP · GBP/JPY",
    "JPY": "USD/JPY · EUR/JPY · GBP/JPY",
    "AUD": "AUD/USD · AUD/JPY · AUD/NZD",
    "NZD": "NZD/USD · AUD/NZD · NZD/JPY",
    "CAD": "USD/CAD · CAD/JPY · EUR/CAD",
    "CHF": "USD/CHF · EUR/CHF · CHF/JPY",
}


def now_myt():
    return datetime.now(MYT)


def esc(value):
    return html.escape(str(value or ""), quote=False)


def default_state(today):
    return {
        "date": today,
        "daily_calendar_msg_id": None,
        "daily_calendar_hash": None,
        "sent_warnings": [],
        "sent_announcements": [],
    }


def load_state():
    today = now_myt().strftime("%Y-%m-%d")
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        state = default_state(today)
    if state.get("date") != today:
        state = default_state(today)
    for key in ("sent_warnings", "sent_announcements"):
        state.setdefault(key, [])
    return state


def save_state(state):
    temporary = STATE_FILE + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, STATE_FILE)


def request_json(url, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    attempts = 3 if data is None else 1  # Never retry Telegram POSTs automatically.
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == attempts:
                raise RuntimeError(f"Request failed: {exc}") from exc
            time.sleep(attempt * 2)


def fetch_events():
    print(f"Fetching Forex Factory calendar at {now_myt():%Y-%m-%d %H:%M:%S} MYT")
    data = request_json(FEED_URL)
    if not isinstance(data, list) or not data:
        raise RuntimeError("Calendar feed returned no events")
    return data


def parse_events(data):
    today = now_myt().date()
    events = []
    for item in data:
        currency = str(item.get("country") or item.get("Country") or "").upper()
        impact = str(item.get("impact") or item.get("Impact") or "").lower()
        if currency not in CURRENCIES or impact not in IMPACTS:
            continue
        raw_date = item.get("date") or item.get("Date")
        if not raw_date:
            continue
        try:
            event_time = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00")).astimezone(MYT)
        except (TypeError, ValueError) as exc:
            print(f"Skipping malformed event date {raw_date!r}: {exc}")
            continue
        if event_time.date() != today:
            continue
        events.append({
            "datetime": event_time,
            "currency": currency,
            "impact": impact,
            "title": str(item.get("title") or item.get("Title") or "Untitled event"),
            "forecast": str(item.get("forecast") or item.get("Forecast") or ""),
            "previous": str(item.get("previous") or item.get("Previous") or ""),
            "actual": str(item.get("actual") or item.get("Actual") or ""),
        })
    return sorted(events, key=lambda event: event["datetime"])


def event_id(event):
    raw = f"{event['datetime'].isoformat()}|{event['currency']}|{event['title']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def comparison(actual, forecast):
    if not actual or not forecast:
        return ""
    number = r"[-+]?\d+(?:\.\d+)?"
    import re
    actual_match = re.search(number, actual.replace(",", ""))
    forecast_match = re.search(number, forecast.replace(",", ""))
    if not actual_match or not forecast_match:
        return ""
    actual_value, forecast_value = float(actual_match.group()), float(forecast_match.group())
    if actual_value > forecast_value:
        return "📈 Actual came in above forecast"
    if actual_value < forecast_value:
        return "📉 Actual came in below forecast"
    return "➖ Actual matched forecast"


def event_lines(event, include_pairs=False):
    marker = IMPACT_EMOJI.get(event["impact"], "⚪")
    lines = [
        f"{marker} <b>{event['datetime']:%I:%M %p}</b> · <b>{esc(event['currency'])}</b>",
        f"<b>{esc(event['title'])}</b>",
    ]
    values = []
    if event["actual"]:
        values.append(f"Actual: <b>{esc(event['actual'])}</b>")
    if event["forecast"]:
        values.append(f"Forecast: {esc(event['forecast'])}")
    if event["previous"]:
        values.append(f"Previous: {esc(event['previous'])}")
    if values:
        lines.append(" · ".join(values))
    if include_pairs and PAIR_MAP.get(event["currency"]):
        lines.append(f"Pairs to watch: <i>{PAIR_MAP[event['currency']]}</i>")
    return lines


def build_overview(events):
    current = now_myt()
    lines = [
        "📅 <b>FOREX ECONOMIC CALENDAR</b>",
        f"<b>{current:%A, %d %B %Y}</b>",
        "🇲🇾 Malaysia Time (MYT)",
        f"Filter: {', '.join(CURRENCIES)} · {', '.join(x.upper() for x in IMPACTS)}",
        "────────────────────",
    ]
    if not events:
        lines.extend(["", "✅ <i>No matching events scheduled for today.</i>"])
    else:
        for event in events:
            lines.extend(["", *event_lines(event)])
        lines.extend(["", "⚠️ <i>Timing may change. Manage risk around major releases.</i>"])
    message = "\n".join(lines)
    if len(message) > MAX_MESSAGE_LENGTH:
        message = message[: MAX_MESSAGE_LENGTH - 80] + "\n\n<i>Additional events omitted due to message length.</i>"
    return message


def telegram(method, payload):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not configured")
    payload["chat_id"] = CHAT_ID
    payload["parse_mode"] = "HTML"
    payload["disable_web_page_preview"] = True
    result = request_json(f"https://api.telegram.org/bot{TOKEN}/{method}", payload)
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected {method}: {result.get('description', 'unknown error')}")
    return result["result"]


def send_message(text):
    result = telegram("sendMessage", {"text": text})
    print(f"Telegram message sent successfully (message id: {result['message_id']})")
    return result["message_id"]


def edit_message(message_id, text):
    try:
        telegram("editMessageText", {"message_id": message_id, "text": text})
        print(f"Daily overview updated (message id: {message_id})")
    except RuntimeError as exc:
        if "message is not modified" not in str(exc).lower():
            raise


def should_create_overview(state, current):
    if RUN_MODE in {"all", "overview"}:
        return True
    return state.get("daily_calendar_msg_id") is None and 7 <= current.hour < 12


def process_overview(events, state):
    message = build_overview(events)
    digest = hashlib.sha256(message.encode()).hexdigest()
    message_id = state.get("daily_calendar_msg_id")
    if not message_id:
        state["daily_calendar_msg_id"] = send_message(message)
        state["daily_calendar_hash"] = digest
        return True
    if state.get("daily_calendar_hash") != digest:
        edit_message(message_id, message)
        state["daily_calendar_hash"] = digest
        return True
    print("Daily overview unchanged; no Telegram edit needed")
    return False


def process_alerts(events, state):
    current = now_myt()
    changed = False
    for event in events:
        identifier = event_id(event)
        seconds_until = (event["datetime"] - current).total_seconds()
        if 0 < seconds_until <= 10 * 60 and identifier not in state["sent_warnings"]:
            minutes = max(1, round(seconds_until / 60))
            message = "\n".join([
                f"⚠️ <b>NEWS ALERT · {minutes} MINUTES</b>",
                "────────────────────",
                *event_lines(event, include_pairs=True),
                "",
                "🛡 <i>Expect volatility, wider spreads and possible slippage.</i>",
            ])
            send_message(message)
            state["sent_warnings"].append(identifier)
            changed = True
        if seconds_until <= 0 and event["actual"] and identifier not in state["sent_announcements"]:
            comparison_text = comparison(event["actual"], event["forecast"])
            lines = [
                "📢 <b>FOREX NEWS RELEASED</b>",
                "────────────────────",
                *event_lines(event, include_pairs=True),
            ]
            if comparison_text:
                lines.extend(["", f"{comparison_text}."])
            lines.extend(["", "<i>Above/below forecast is not automatically bullish or bearish; interpretation depends on the indicator.</i>"])
            send_message("\n".join(lines))
            state["sent_announcements"].append(identifier)
            changed = True
    return changed


def main():
    print(f"Forex Event Bot v2 starting in {RUN_MODE!r} mode")
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Required Telegram configuration is missing")
    events = parse_events(fetch_events())
    print(f"Found {len(events)} matching event(s) for today")
    state = load_state()
    changed = False
    if should_create_overview(state, now_myt()):
        changed = process_overview(events, state) or changed
    if RUN_MODE != "overview":
        changed = process_alerts(events, state) or changed
        if state.get("daily_calendar_msg_id"):
            changed = process_overview(events, state) or changed
    save_state(state)
    print(f"Bot cycle finished; state changed: {changed}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
