# Crypto Price Alert Bot + Screener + Backtester

Three scripts:
- **`bot.py`** — watches a specific coin (or short list) you choose, alerts on signals.
- **`scanner.py`** — scans the *entire* liquid Binance USDT market and sends
  you a ranked digest of every coin currently showing a signal. Use this
  one if you want "show me all coins with potential right now."
- **`backtest.py`** — tests the strategy against real historical data so
  you know whether it actually would have made money BEFORE trusting it.
  **Run this first**, before relying on the alerts.

All three use the same RSI + moving-average signals.
**This is a decision-support and research tool, not financial advice or
a guaranteed prediction system** — always do your own research before
trading.

> **Note:** `bot.py` uses CoinGecko's free API for price data (not Binance).
> Binance blocks most cloud/datacenter server IPs (Railway, Render, AWS,
> etc.) with a 451 error regardless of region, so CoinGecko is used
> instead since it works reliably from cloud hosts. `scanner.py` and
> `backtest.py` still use Binance and are best run locally, or would
> need a similar CoinGecko rewrite to run on Railway.

## What it actually does

- Pulls recent price history for coins (one coin for `bot.py`, hundreds for `scanner.py`).
- Calculates RSI (14-period) and two moving averages (20 & 50 by default).
- Flags a coin when:
  - RSI drops below 30 (historically "oversold") or above 70 ("overbought")
  - The short MA crosses above the long MA ("golden cross" — bullish) or
    below it ("death cross" — bearish)
- `scanner.py` ranks flagged coins by signal strength and sends the top 15
  in one digest message, filtering out illiquid/low-volume coins first.

## Setup (10 minutes)

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Create a Telegram bot
1. Open Telegram, search for **@BotFather**, start a chat.
2. Send `/newbot`, follow the prompts (pick a name and username).
3. BotFather gives you a **token** like `123456789:AAExampleTokenHere`. Save it.

### 3. Get your chat ID
1. Search for your new bot in Telegram and send it any message (e.g. "hi").
2. In your browser, visit (replace TOKEN with your bot token):
