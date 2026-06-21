name: Forex Calendar Notifier

on:
  schedule:
    # 7:00 AM MYT = 23:00 UTC (previous day)
    - cron: "0 23 * * *"
  workflow_dispatch: # Allow manual trigger from GitHub UI

jobs:
  send-forex-calendar:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run Forex Notifier
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python forex_notify.py
