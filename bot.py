"""
Crypto Price Alert Bot
-----------------------
Watches coin prices on Binance and sends you a Telegram message when
technical indicators (RSI + moving average crossover) hit levels that
are historically considered "worth a look."

IMPORTANT: This is a decision-support tool, not financial advice.
Signals are based on past price patterns and can be wrong. Always do
your own research and never risk money you can't afford to lose.

SETUP (see README.md for full steps):
1. Create a Telegram bot via @BotFather, get the bot token.
2. Message your bot once, then get your chat_id (see README).
3. Fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID below (or set as
   environment variables of the same name).
4. pip install -r requirements.txt
5. python bot.py
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone

# ============ CONFIG ============

# Coins to watch (Binance symbol format, e.g. BTCUSDT, ETHUSDT)
COINS = ["BTCUSDT"]

# Candle timeframe: 1m, 5m, 15m, 1h, 4h, 1d
INTERVAL = "1h"

# How often to check for signals (seconds). 300 = 5 minutes.
CHECK_INTERVAL_SECONDS = 300

# RSI settings
RSI_PERIOD = 14
RSI_OVERSOLD = 30      # below this = potential buy zone
RSI_OVERBOUGHT = 70    # above this = potential sell zone

# Moving average crossover settings
MA_SHORT = 20
MA_LONG = 50

# Telegram credentials — fill these in or set as environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "PUT_YOUR_CHAT_ID_HERE")

# ============ END CONFIG ============

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

# Track last signal per coin so we don't spam the same alert every cycle
_last_signal_sent = {}


def get_klines(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    """Fetch recent candlestick data from Binance public API (no key needed)."""
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=10)
    resp.raise_for_status()
    raw = resp.json()

    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["close"] = df["close"].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def analyze(symbol: str) -> dict:
    df = get_klines(symbol, INTERVAL)
    df["rsi"] = compute_rsi(df["close"], RSI_PERIOD)
    df["ma_short"] = df["close"].rolling(MA_SHORT).mean()
    df["ma_long"] = df["close"].rolling(MA_LONG).mean()

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    signals = []

    # RSI signals
    if latest["rsi"] < RSI_OVERSOLD:
        signals.append(f"RSI oversold ({latest['rsi']:.1f}) — historically a potential buy zone")
    elif latest["rsi"] > RSI_OVERBOUGHT:
        signals.append(f"RSI overbought ({latest['rsi']:.1f}) — historically a potential sell zone")

    # MA crossover signals (golden cross / death cross)
    if prev["ma_short"] <= prev["ma_long"] and latest["ma_short"] > latest["ma_long"]:
        signals.append(f"Golden cross: {MA_SHORT}-MA crossed above {MA_LONG}-MA — bullish signal")
    elif prev["ma_short"] >= prev["ma_long"] and latest["ma_short"] < latest["ma_long"]:
        signals.append(f"Death cross: {MA_SHORT}-MA crossed below {MA_LONG}-MA — bearish signal")

    return {
        "symbol": symbol,
        "price": latest["close"],
        "rsi": latest["rsi"],
        "signals": signals,
        "time": latest["open_time"],
    }


def send_telegram_message(text: str):
    if "PUT_YOUR" in TELEGRAM_BOT_TOKEN or "PUT_YOUR" in TELEGRAM_CHAT_ID:
        print("[WARN] Telegram credentials not set. Message not sent:")
        print(text)
        return

    url = TELEGRAM_API_URL.format(token=TELEGRAM_BOT_TOKEN)
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, data=payload, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] Failed to send Telegram message: {e}")


def format_alert(result: dict) -> str:
    lines = [
        f"*{result['symbol']} Alert*",
        f"Price: ${result['price']:.2f}",
        f"RSI: {result['rsi']:.1f}",
        "",
    ]
    lines.extend(f"• {s}" for s in result["signals"])
    lines.append("")
    lines.append("_Not financial advice. Do your own research._")
    return "\n".join(lines)


def run_once():
    for symbol in COINS:
        try:
            result = analyze(symbol)
        except Exception as e:
            print(f"[ERROR] Failed to analyze {symbol}: {e}")
            continue

        if result["signals"]:
            # Avoid re-sending the exact same signal set back-to-back
            signature = tuple(result["signals"])
            if _last_signal_sent.get(symbol) != signature:
                message = format_alert(result)
                print(f"[{datetime.now(timezone.utc)}] Sending alert for {symbol}")
                send_telegram_message(message)
                _last_signal_sent[symbol] = signature
        else:
            print(f"[{datetime.now(timezone.utc)}] {symbol}: no signal (price ${result['price']:.2f}, RSI {result['rsi']:.1f})")


def main():
    print("Crypto Alert Bot started.")
    print(f"Watching: {COINS} on {INTERVAL} candles, checking every {CHECK_INTERVAL_SECONDS}s")
    while True:
        run_once()
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
