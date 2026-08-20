"""
Small-Cap Coin Scanner
------------------------
Pulls details for every actively-tracked coin on CoinGecko whose market cap
falls in a configurable "small-cap" range, and sends the full list to
Telegram (in chunks, since Telegram has a message-length limit) plus saves
a CSV with every field for coins you want to dig into further.

Uses CoinGecko (like bot.py) rather than Binance, since Binance blocks most
cloud/datacenter IPs AND doesn't list most small/micro-cap coins at all —
CoinGecko tracks thousands more of them.

Note: only coins CoinGecko actively tracks are included — extremely new,
unlisted, or obscure tokens may not appear yet.

This is a decision-support tool, not financial advice. Small-cap coins are
high-risk and often illiquid (hard to buy/sell without moving the price a
lot) — always do your own research before acting on anything this sends.

SETUP: same as bot.py — fill in TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in
bot.py (this script reuses them), then just run:
    python smallcoins.py
"""

import csv
import time
import requests
from datetime import datetime, timezone

from bot import send_telegram_message, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# ============ CONFIG ============

# "Small-cap" range in USD. There's no official definition — adjust to
# taste. A common rough split: micro-cap < $50M, small-cap $50M-$300M.
MIN_MARKET_CAP_USD = 100_000       # filters out dust / near-worthless tokens
MAX_MARKET_CAP_USD = 50_000_000    # anything above this is skipped

# CoinGecko free tier: max 250 results per page, shared rate limit
# (~10-30 calls/min across all free users) — don't lower the delay much.
PER_PAGE = 250
MAX_PAGES = 40                  # safety cap so this can't run forever
REQUEST_DELAY_SECONDS = 1.5     # be polite to the free API

# How many coins per Telegram message (keeps each message under Telegram's
# ~4096 character limit)
COINS_PER_MESSAGE = 25

CSV_FILENAME = "small_cap_coins.csv"

# ============ END CONFIG ============

COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"


def fetch_small_cap_coins() -> list:
    """
    Page through CoinGecko's market list, ordered by market cap ascending,
    collecting every coin whose market cap sits inside the configured range.
    Stops once market caps exceed MAX_MARKET_CAP_USD (since the list is
    sorted ascending, everything after that point is even bigger, so no
    point paging further).
    """
    results = []
    for page in range(1, MAX_PAGES + 1):
        params = {
            "vs_currency": "usd",
            "order": "market_cap_asc",
            "per_page": PER_PAGE,
            "page": page,
            "sparkline": "false",
            "price_change_percentage": "24h",
        }
        resp = requests.get(COINGECKO_MARKETS_URL, params=params, timeout=20)
        resp.raise_for_status()
        batch = resp.json()

        if not batch:
            break  # ran out of coins

        stop = False
        for coin in batch:
            mc = coin.get("market_cap")
            if mc is None:
                continue  # no market cap data for this one, skip it
            if mc < MIN_MARKET_CAP_USD:
                continue  # too small / likely dust or effectively delisted
            if mc > MAX_MARKET_CAP_USD:
                stop = True
                break  # ascending order — everything after is bigger too
            results.append(coin)

        print(f"[{datetime.now(timezone.utc)}] Page {page}: "
              f"{len(results)} small-cap coin(s) collected so far")

        if stop:
            break
        time.sleep(REQUEST_DELAY_SECONDS)

    return results


def save_csv(coins: list, filename: str = CSV_FILENAME):
    fields = ["symbol", "name", "current_price", "market_cap",
              "market_cap_rank", "total_volume", "price_change_percentage_24h"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for c in coins:
            writer.writerow(c)
    print(f"Saved {len(coins)} coins to {filename}")


def format_chunk(coins: list, chunk_num: int, total_chunks: int) -> str:
    lines = [f"*Small-Cap Coins ({chunk_num}/{total_chunks})*", ""]
    for c in coins:
        price = c.get("current_price") or 0
        mc = c.get("market_cap") or 0
        vol = c.get("total_volume") or 0
        chg = c.get("price_change_percentage_24h")
        chg_str = f"{chg:+.1f}%" if chg is not None else "n/a"
        lines.append(
            f"• *{c['symbol'].upper()}* ({c['name']}) — "
            f"${price:.6f} | MCap ${mc:,.0f} | Vol ${vol:,.0f} | 24h {chg_str}"
        )
    lines.append("")
    lines.append("_Small-cap coins are high-risk and often illiquid. "
                  "Not financial advice — verify before acting._")
    return "\n".join(lines)


def run():
    print(f"Fetching coins with market cap between "
          f"${MIN_MARKET_CAP_USD:,.0f} and ${MAX_MARKET_CAP_USD:,.0f}...")
    coins = fetch_small_cap_coins()
    print(f"Found {len(coins)} small-cap coin(s) total.")

    if not coins:
        send_telegram_message(
            "*Small-Cap Coin Scan*\nNo coins found in the configured market cap range."
        )
        return

    save_csv(coins)

    chunks = [coins[i:i + COINS_PER_MESSAGE] for i in range(0, len(coins), COINS_PER_MESSAGE)]
    for i, chunk in enumerate(chunks, start=1):
        message = format_chunk(chunk, i, len(chunks))
        send_telegram_message(message)
        time.sleep(1)  # avoid Telegram rate limits

    print(f"Sent {len(chunks)} Telegram message(s) covering {len(coins)} coins. "
          f"Full details also saved to {CSV_FILENAME}.")


if __name__ == "__main__":
    run()
