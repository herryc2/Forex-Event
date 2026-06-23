import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ===== Config & Setup =====

# Timezone config: Primary uses standard zoneinfo, fallback to UTC+8 if tzdata is not installed.
try:
    from zoneinfo import ZoneInfo
    MYT = ZoneInfo("Asia/Kuala_Lumpur")
except Exception:
    MYT = timezone(timedelta(hours=8))

# Telegram credentials
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Customizable settings (via env variables or defaults)
CURRENCIES = [c.strip().upper() for c in os.environ.get("CURRENCIES", "USD").split(",") if c.strip()]
IMPACT_LEVELS = [i.strip().lower() for i in os.environ.get("IMPACT_LEVELS", "high,medium").split(",") if i.strip()]

# Impact emoji markers
IMPACT_EMOJI = {
    "high": "🔴",
    "medium": "🟠",
    "low": "🟡",
    "none": "⚪"
}

CACHE_FILE = ".calendar_cache.json"
STATE_FILE = ".bot_state.json"
FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ===== Helpers =====

def get_myt_now():
    """Returns the current datetime in Malaysia Time (MYT)."""
    return datetime.now(MYT)

def escape_html(text):
    """Escapes HTML characters to prevent Telegram API parsing errors."""
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def load_state():
    """Loads the current bot state from a local file, resetting it if a new day has started."""
    today_str = get_myt_now().strftime("%Y-%m-%d")
    default_state = {
        "date": today_str,
        "daily_calendar_msg_id": None,
        "sent_warnings": [],
        "sent_announcements": []
    }
    
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            # Reset state on a new day
            if state.get("date") != today_str:
                print(f"ℹ️ New day detected ({today_str}). Resetting bot state.")
                save_state(default_state)
                return default_state
            return state
        except Exception as e:
            print(f"⚠️ Error reading state file: {e}")
            
    return default_state

def save_state(state):
    """Saves the bot state to the local file."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error writing to state file: {e}")

def get_event_id(e):
    """Generates a unique identifier for an event based on its datetime, country, and title."""
    date_part = e["datetime"].isoformat() if isinstance(e.get("datetime"), datetime) else str(e.get("datetime"))
    return f"{date_part}_{e.get('country')}_{e.get('title')}"

def fetch_calendar_data():
    """
    Fetches the JSON calendar data from Forex Factory feed.
    If the fetch fails (e.g. Cloudflare 429 rate limit or network issue),
    it will fall back to reading from a locally cached file.
    """
    print(f"[{get_myt_now().strftime('%Y-%m-%d %H:%M:%S')}] Fetching calendar feed from {FEED_URL}...")
    
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": USER_AGENT})
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read().decode("utf-8")
            data = json.loads(content)
            
            # Save to cache
            try:
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print("✅ Feed fetched successfully and saved to local cache.")
            except Exception as cache_err:
                print(f"⚠️ Warning: Could not write to cache file: {cache_err}")
                
            return data
            
    except urllib.error.HTTPError as e:
        print(f"⚠️ HTTP Error: {e.code} {e.reason}")
        if e.code == 429:
            print("⚠️ Rate limit (429) hit. Attempting to fall back to cached calendar data...")
        return load_cached_data()
    except Exception as e:
        print(f"⚠️ Network/Fetch Error: {e}")
        return load_cached_data()

def load_cached_data():
    """Loads the calendar data from the local cache file."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            print("ℹ️ Successfully loaded calendar data from local cache.")
            return data
        except Exception as e:
            print(f"❌ Error reading cache file: {e}")
    else:
        print("❌ Local cache file does not exist.")
    return []

def get_todays_events(data):
    """
    Processes the raw JSON feed data, filters for targeted currencies and impact levels,
    converts date times to MYT, and isolates today's events.
    """
    today_myt = get_myt_now().strftime("%Y-%m-%d")
    events = []
    
    for item in data:
        country = str(item.get("country") or item.get("Country") or "").upper()
        if country not in CURRENCIES:
            continue
            
        impact = str(item.get("impact") or item.get("Impact") or "").lower()
        if impact not in IMPACT_LEVELS:
            continue
            
        date_str = item.get("date") or item.get("Date")
        if not date_str:
            continue
            
        try:
            # Parse ISO 8601 date string (supports timezone offsets natively)
            event_dt = datetime.fromisoformat(date_str)
            # Convert to MYT
            myt_dt = event_dt.astimezone(MYT)
            
            # Filter for events occurring today in Malaysia Time
            if myt_dt.strftime("%Y-%m-%d") != today_myt:
                continue
                
            events.append({
                "datetime": myt_dt,
                "time_str": myt_dt.strftime("%I:%M %p"),
                "impact": impact,
                "country": country,
                "title": item.get("title") or item.get("Title") or "",
                "forecast": item.get("forecast") or item.get("Forecast") or "",
                "previous": item.get("previous") or item.get("Previous") or "",
                "actual": item.get("actual") or item.get("Actual") or ""
            })
        except Exception as e:
            # Skip individually malformed events without failing the entire run
            print(f"⚠️ Skip event parsing: {e} for item: {item}")
            
    # Sort events chronologically by their datetime objects
    events.sort(key=lambda x: x["datetime"])
    return events

def format_html_message(events):
    """Formats the list of events into a premium Telegram HTML message."""
    today = get_myt_now().strftime("%A, %d %B %Y")
    
    # Header
    msg = (
        f"📅 <b>Economic Calendar</b>\n"
        f"<b>Date:</b> {today}\n"
        f"<b>Timezone:</b> Malaysia Time (MYT)\n"
        f"<b>Filter:</b> {', '.join(CURRENCIES)} | {', '.join([i.upper() for i in IMPACT_LEVELS])}\n\n"
    )
    
    if not events:
        msg += "✅ <i>No matching events scheduled for today.</i>"
        return msg
        
    for e in events:
        emoji = IMPACT_EMOJI.get(e["impact"], "⚪")
        
        # Event title row: [Emoji] [Time] - [Country]: [Title]
        msg += f"{emoji} <b>{e['time_str']}</b> - <b>{escape_html(e['country'])}</b>\n"
        msg += f"👉 <code>{escape_html(e['title'])}</code>\n"
        
        # Details row
        details = []
        if e["forecast"]:
            details.append(f"Act: {escape_html(e['actual']) if e['actual'] else '⌛'}")
            details.append(f"Fcst: {escape_html(e['forecast'])}")
        if e["previous"]:
            details.append(f"Prev: {escape_html(e['previous'])}")
            
        if details:
            msg += f"<blockquote>{ ' | '.join(details) }</blockquote>\n"
        else:
            msg += "\n"
            
    return msg

def send_telegram(message):
    """Sends the formatted HTML message to Telegram and returns the message ID if successful."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Error: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables are not set.")
        print("Stdout representation of the message:")
        print(message)
        # Mock message ID for testing
        return 999999
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            resp_data = json.loads(response.read().decode("utf-8"))
            if resp_data.get("ok"):
                msg_id = resp_data["result"]["message_id"]
                print(f"✅ Telegram message sent successfully! Message ID: {msg_id}")
                return msg_id
            else:
                print(f"❌ Telegram API Error: {resp_data}")
                return None
    except urllib.error.HTTPError as e:
        print(f"❌ Telegram HTTP Error: {e.code} {e.reason}")
        try:
            print("Response:", e.read().decode("utf-8"))
        except Exception:
            pass
        return None
    except Exception as e:
        print(f"❌ Telegram Send Error: {e}")
        return None

def edit_telegram_message(message_id, new_text):
    """Edits an existing Telegram message with new HTML content."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"⚠️ Simulated Telegram Edit (Message {message_id}):")
        print(new_text)
        print("------------------------------------------")
        return True
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_id": message_id,
        "text": new_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            resp_data = json.loads(response.read().decode("utf-8"))
            if resp_data.get("ok"):
                print(f"✅ Telegram message {message_id} updated successfully!")
                return True
            else:
                print(f"❌ Telegram Edit API Error: {resp_data}")
                return False
    except urllib.error.HTTPError as e:
        print(f"❌ Telegram Edit HTTP Error: {e.code} {e.reason}")
        return False
    except Exception as e:
        print(f"❌ Telegram Edit Error: {e}")
        return False

def main():
    print("Forex Economic Calendar Bot starting...")
    
    # 1. Fetch
    raw_data = fetch_calendar_data()
    if not raw_data:
        print("❌ No calendar data retrieved. Exiting.")
        return
        
    # 2. Filter & Process
    events = get_todays_events(raw_data)
    print(f"Found {len(events)} matching events for today.")
    
    # 3. Load state
    state = load_state()
    now = get_myt_now()
    state_updated = False
    
    # 4. Check/Send Daily Calendar Overview
    current_overview = format_html_message(events)
    if not state.get("daily_calendar_msg_id"):
        print("Sending initial daily calendar overview...")
        msg_id = send_telegram(current_overview)
        if msg_id:
            state["daily_calendar_msg_id"] = msg_id
            state_updated = True
    else:
        print(f"Updating existing daily calendar overview message ({state['daily_calendar_msg_id']})...")
        edit_telegram_message(state["daily_calendar_msg_id"], current_overview)
        
    # 5. Check 10-Minute Warnings & Rate Announcements
    for e in events:
        event_id = get_event_id(e)
        event_time = e["datetime"]
        
        # Time difference in seconds between event time and now
        time_diff = (event_time - now).total_seconds()
        
        # A. 10-Minute warning (Trigger if event starts in the next 10 minutes (600s) and has not started yet)
        if 0 < time_diff <= 600:
            if event_id not in state["sent_warnings"]:
                emoji = IMPACT_EMOJI.get(e["impact"], "⚪")
                warning_msg = (
                    f"⚠️ <b>Upcoming Forex Event (10 mins)</b>\n\n"
                    f"{emoji} <b>{e['time_str']}</b> - <b>{escape_html(e['country'])}</b>\n"
                    f"👉 <code>{escape_html(e['title'])}</code>\n"
                )
                if e["forecast"]:
                    warning_msg += f"<blockquote>Fcst: {escape_html(e['forecast'])} | Prev: {escape_html(e['previous'])}</blockquote>"
                
                print(f"Sending 10-minute warning alert for: {e['title']}")
                if send_telegram(warning_msg):
                    state["sent_warnings"].append(event_id)
                    state_updated = True
                    
        # B. Rate announcement (Trigger if event time has passed/is occurring now AND an actual value is available)
        elif time_diff <= 0 and e["actual"]:
            if event_id not in state["sent_announcements"]:
                emoji = IMPACT_EMOJI.get(e["impact"], "⚪")
                announcement_msg = (
                    f"📢 <b>Forex Rate Announced</b>\n\n"
                    f"{emoji} <b>{e['time_str']}</b> - <b>{escape_html(e['country'])}</b>\n"
                    f"👉 <code>{escape_html(e['title'])}</code>\n"
                    f"<blockquote>Act: <b>{escape_html(e['actual'])}</b> | Fcst: {escape_html(e['forecast'])} | Prev: {escape_html(e['previous'])}</blockquote>"
                )
                
                print(f"Sending rate announcement alert for: {e['title']}")
                if send_telegram(announcement_msg):
                    state["sent_announcements"].append(event_id)
                    state_updated = True
                    
    if state_updated:
        save_state(state)
        
    print("Bot cycle finished.")

if __name__ == "__main__":
    main()
