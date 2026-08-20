"""
Small Coin Scanner
--------------------
Pulls details for every actively-tracked coin on CoinGecko trading under a
configurable price (default: under $1 — "penny coins"), optionally also
bounded by market cap, and sends the full list to Telegram (in chunks,
since Telegram has a message-length limit) plus saves a CSV with every
field for coins you want to dig into further.

Uses CoinGecko (like bot.py) rather than Binance, since Binance blocks most
cloud/datacenter IPs AND doesn't list most small/obscure coins at all —
CoinGecko tracks thousands more of them.

Note: only coins CoinGecko actively tracks are included — extremely new,
unlisted, or obscure tokens may not appear yet. Also note: "under $1" is
about price PER COIN, not the size of the project — some huge, well-known
coins (with billions in market cap) trade under $1 just because they have
a huge supply. Check market_cap / market_cap_rank in the results too if
you specifically want small/obscure projects rather than just cheap ones.

This is a decision-support tool, not financial advice. Low-priced and
small-cap coins are often high-risk and illiquid (hard to buy/sell without
moving the price a lot) — always do your own research before acting on
anything this sends.

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

# "Small coin" definition. You can filter by price, market cap, or both —
# a coin only needs to pass whichever filters are turned on below.

# Price filter: only include coins trading under this price (e.g. penny
# coins). Set to None to disable price filtering entirely.
MAX_PRICE_USD = 1.0

# Market cap filter (optional, in USD). Set MAX_MARKET_CAP_USD to None to
# disable and rely on price alone. MIN_MARKET_CAP_USD still filters out
# complete dust/delisted tokens with near-zero market cap either way.
MIN_MARKET_CAP_USD = 100_000       # filters out dust / near-worthless tokens
MAX_MARKET_CAP_USD = None          # e.g. 50_000_000 to also cap by market cap

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
    Page through CoinGecko's market list (largest market cap first, so
    well-known coins are checked before obscure ones), collecting every
    coin that passes the configured filters (price under MAX_PRICE_USD,
    and/or within the market cap range).
    """
    results = []
    for page in range(1, MAX_PAGES + 1):
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
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

        for coin in batch:
            price = coin.get("current_price")
            mc = coin.get("market_cap")

            if MAX_PRICE_USD is not None:
                if price is None or price >= MAX_PRICE_USD:
                    continue  # too expensive to count as "small"

            if mc is None:
                continue  # no market cap data at all, skip it
            if mc < MIN_MARKET_CAP_USD:
                continue  # too small / likely dust or effectively delisted
            if MAX_MARKET_CAP_USD is not None and mc > MAX_MARKET_CAP_USD:
                continue  # too big for the configured cap, skip it
            results.append(coin)

        print(f"[{datetime.now(timezone.utc)}] Page {page}: "
              f"{len(results)} small coin(s) collected so far")

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
    lines = [f"*Coins Under ${MAX_PRICE_USD:g} ({chunk_num}/{total_chunks})*", ""]
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
    lines.append("_Low-priced and small-cap coins are often high-risk and illiquid. "
                  "Not financial advice — verify before acting._")
    return "\n".join(lines)


def run():
    price_desc = f"under ${MAX_PRICE_USD:g}" if MAX_PRICE_USD is not None else "any price"
    cap_desc = f"${MIN_MARKET_CAP_USD:,.0f}+" if MAX_MARKET_CAP_USD is None \
        else f"${MIN_MARKET_CAP_USD:,.0f}-${MAX_MARKET_CAP_USD:,.0f}"
    print(f"Fetching coins priced {price_desc}, market cap {cap_desc}...")
    coins = fetch_small_cap_coins()
    print(f"Found {len(coins)} matching coin(s) total.")

    if not coins:
        send_telegram_message(
            "*Small Coin Scan*\nNo coins found matching the configured filters."
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
