import importlib.util
import os
from datetime import datetime

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "test")

spec = importlib.util.spec_from_file_location("bot", "forex_notify.py")
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)

sample = [{
    "country": "USD",
    "impact": "High",
    "date": datetime.now(bot.MYT).replace(hour=20, minute=30).isoformat(),
    "title": "CPI <Final>",
    "forecast": "2.8%",
    "previous": "2.7%",
    "actual": "3.0%",
}]

events = bot.parse_events(sample)
assert len(events) == 1
assert "&lt;Final&gt;" in bot.build_overview(events)
assert bot.comparison("3.0%", "2.8%") == "📈 Actual came in above forecast"
assert bot.event_id(events[0]) == bot.event_id(events[0])
assert len(bot.build_overview(events)) < 4096

print("All Forex bot tests passed")
