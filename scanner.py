"""
Crypto Screener Bot
--------------------
Scans ALL actively-traded USDT pairs on Binance (not just BTC), runs the
same RSI + moving-average analysis on each, and sends you a single ranked
Telegram digest of the coins currently showing a signal.

This is a decision-support tool, not financial advice. Indicators describe
what already happened in the price — they don't predict the future. Do
your own research before acting on anything this sends you.

Builds on bot.py — run that first to make sure your Telegram credentials
work, then use this for the full-market scan.

SETUP: same as bot.py (see README.md). Just run:
    python scanner.py
"""

import time
import requests
import pandas as pd
from datetime import datetime, timezone

from bot import (
    compute_rsi,
    send_telegram_message,
    RSI_PERIOD,
    RSI_OVERSOLD,
    RSI_OVERBOUGHT,
    MA_SHORT,
    MA_LONG,
    INTERVAL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)

# ============ CONFIG ============

# Only scan coins with at least this much 24h trading volume in USDT.
# Filters out dead/illiquid coins that are risky to trade and noisy to scan.
MIN_24H_VOLUME_USD = 5_000_000

# How many coins to include in the digest, ranked by signal strength
TOP_N_RESULTS = 15

# How often to run a full market scan (seconds). Scanning ~150-300 coins
# takes a few minutes due to Binance rate limits, so don't go too low.
SCAN_INTERVAL_SECONDS = 1800  # 30 minutes

# Pause between individual coin requests to respect Binance rate limits
REQUEST_DELAY_SECONDS = 0.15

# ============ END CONFIG ============

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_TICKER_24H_URL = "https://api.binance.com/api/v3/ticker/24hr"
BINANCE_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo"


def get_liquid_usdt_symbols(min_volume_usd: float) -> list:
    """Return USDT trading pairs with enough 24h volume to be worth scanning."""
    info_resp = requests.get(BINANCE_EXCHANGE_INFO_URL, timeout=15)
    info_resp.raise_for_status()
    symbols_info = info_resp.json()["symbols"]

    tradeable = {
        s["symbol"] for s in symbols_info
        if s["quoteAsset"] == "USDT"
        and s["status"] == "TRADING"
        and s["isSpotTradingAllowed"]
    }

    ticker_resp = requests.get(BINANCE_TICKER_24H_URL, timeout=15)
    ticker_resp.raise_for_status()
    tickers = ticker_resp.json()

    liquid = [
        t["symbol"] for t in tickers
        if t["symbol"] in tradeable
        and float(t["quoteVolume"]) >= min_volume_usd
    ]
    return sorted(liquid)


def get_klines(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
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
    return df


def analyze_symbol(symbol: str) -> dict | None:
    """Return signal info for one symbol, or None if no signal / error."""
    try:
        df = get_klines(symbol, INTERVAL)
        if len(df) < MA_LONG + 1:
            return None

        df["rsi"] = compute_rsi(df["close"], RSI_PERIOD)
        df["ma_short"] = df["close"].rolling(MA_SHORT).mean()
        df["ma_long"] = df["close"].rolling(MA_LONG).mean()

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        signal_type = None
        strength = 0.0  # higher = more extreme / notable

        if latest["rsi"] < RSI_OVERSOLD:
            signal_type = "OVERSOLD"
            strength = RSI_OVERSOLD - latest["rsi"]
        elif latest["rsi"] > RSI_OVERBOUGHT:
            signal_type = "OVERBOUGHT"
            strength = latest["rsi"] - RSI_OVERBOUGHT

        golden_cross = prev["ma_short"] <= prev["ma_long"] and latest["ma_short"] > latest["ma_long"]
        death_cross = prev["ma_short"] >= prev["ma_long"] and latest["ma_short"] < latest["ma_long"]

        crossover = None
        if golden_cross:
            crossover = "GOLDEN_CROSS"
            strength += 5  # crossovers are rarer/more notable, weight them up
        elif death_cross:
            crossover = "DEATH_CROSS"
            strength += 5

        if signal_type is None and crossover is None:
            return None

        return {
            "symbol": symbol,
            "price": latest["close"],
            "rsi": latest["rsi"],
            "signal_type": signal_type,
            "crossover": crossover,
            "strength": strength,
        }
    except Exception as e:
        print(f"[WARN] Skipping {symbol}: {e}")
        return None


def format_digest(results: list) -> str:
    if not results:
        return "*Market Scan*\nNo coins showing RSI or MA-crossover signals right now."

    lines = [f"*Market Scan — {len(results)} coin(s) showing signals*", ""]
    for r in results[:TOP_N_RESULTS]:
        tags = []
        if r["signal_type"] == "OVERSOLD":
            tags.append("RSI Oversold")
        elif r["signal_type"] == "OVERBOUGHT":
            tags.append("RSI Overbought")
        if r["crossover"] == "GOLDEN_CROSS":
            tags.append("Golden Cross")
        elif r["crossover"] == "DEATH_CROSS":
            tags.append("Death Cross")

        lines.append(
            f"• *{r['symbol']}* — ${r['price']:.4f} — RSI {r['rsi']:.1f} — {', '.join(tags)}"
        )

    lines.append("")
    lines.append("_Ranked by signal strength. Not financial advice — verify before acting._")
    return "\n".join(lines)


def run_scan():
    print(f"[{datetime.now(timezone.utc)}] Fetching liquid USDT pairs...")
    symbols = get_liquid_usdt_symbols(MIN_24H_VOLUME_USD)
    print(f"Scanning {len(symbols)} coins (min 24h volume ${MIN_24H_VOLUME_USD:,.0f})...")

    results = []
    for i, symbol in enumerate(symbols):
        result = analyze_symbol(symbol)
        if result:
            results.append(result)
        time.sleep(REQUEST_DELAY_SECONDS)
        if (i + 1) % 50 == 0:
            print(f"  ...scanned {i + 1}/{len(symbols)}")

    results.sort(key=lambda r: r["strength"], reverse=True)

    print(f"Found {len(results)} coin(s) with signals.")
    message = format_digest(results)
    send_telegram_message(message)


def main():
    print("Crypto Screener Bot started.")
    print(f"Min 24h volume: ${MIN_24H_VOLUME_USD:,.0f} | Scan interval: {SCAN_INTERVAL_SECONDS}s")
    while True:
        try:
            run_scan()
        except Exception as e:
            print(f"[ERROR] Scan failed: {e}")
        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
