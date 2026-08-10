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

## What it actually does

- Pulls recent price candles for coins (one coin for `bot.py`, hundreds for `scanner.py`).
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
   ```
   https://api.telegram.org/botTOKEN/getUpdates
   ```
3. Look for `"chat":{"id": 123456789, ...}` in the response — that number is your `chat_id`.

### 4. Add your credentials
Open `bot.py` and replace:
```python
TELEGRAM_BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "PUT_YOUR_CHAT_ID_HERE"
```
with your real values. (Or set them as environment variables of the same name —
better if you plan to put this on GitHub.)

### 5. Backtest before you trust it (recommended first step)
```bash
python backtest.py BTCUSDT 180
```
This fetches 180 days of real historical data for BTCUSDT, simulates the
strategy, and prints:
- Strategy return vs. simple buy-and-hold over the same period
- Number of trades, win rate, max drawdown
- Saves a full trade log to `backtest_trades_BTCUSDT.csv`

Try it on a few different coins and time periods (30, 90, 180, 365 days).
If the strategy consistently underperforms buy-and-hold, that's a strong
signal not to trust its live alerts blindly — tune the RSI/MA settings in
`bot.py` and re-test, or treat alerts as "worth a look" rather than
"trade this."

### 6. Run the live bot
For one coin:
```bash
python bot.py
```
For a full-market scan (all liquid USDT pairs):
```bash
python scanner.py
```
Leave it running. `bot.py` checks every 5 minutes by default; `scanner.py`
scans the whole market every 30 minutes (scanning takes a few minutes due
to Binance rate limits, so keep this interval reasonable).

## Customizing

**`bot.py`** (single/few coins):
- `COINS` — add more, e.g. `["BTCUSDT", "ETHUSDT", "SOLUSDT"]`
- `INTERVAL` — candle size: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`
- `RSI_OVERSOLD` / `RSI_OVERBOUGHT` — tune sensitivity
- `MA_SHORT` / `MA_LONG` — tune the moving average crossover

**`scanner.py`** (full market):
- `MIN_24H_VOLUME_USD` — raise this to only scan bigger, safer coins;
  lower it to include smaller/riskier ones (default $5M — already fairly loose)
- `TOP_N_RESULTS` — how many coins show up in each digest
- `SCAN_INTERVAL_SECONDS` — how often to rescan the whole market
- Same RSI/MA settings as `bot.py`, imported automatically from it

**`backtest.py`**:
- Takes coin and day-count as command-line args: `python backtest.py ETHUSDT 90`
- `TRADING_FEE_PCT` — set to match your actual exchange fee (default 0.1%)
- Uses whatever RSI/MA settings are currently in `bot.py`, so tune those
  first, then re-run the backtest to see the effect

## Running it 24/7 (so you don't have to keep your laptop on)

Free/cheap options to host this so it runs continuously:
- **Railway.app** or **Render.com** — free tier, deploy from GitHub, runs as a background worker.
- **A $4-6/month VPS** (Oracle Cloud has a genuinely free tier) — run with `nohup python bot.py &` or as a systemd service.
- **PythonAnywhere** — free tier supports always-on tasks on paid plans.

## Before you think about selling this to others

1. **Backtest first.** Run the signal logic against months of historical
   data and check if it would've actually made money. Don't trust it just
   because it "sounds right" — most simple indicator strategies lose to
   just holding, especially with fees included.
2. **Add clear disclaimers** anywhere you share signals — you are not
   licensed to give financial advice, and implying guaranteed returns can
   get you in real legal trouble.
3. Consider whether you're comfortable with the responsibility of people
   acting on your bot's signals with real money.

## Known limitations

- Binance's public API has rate limits — don't set `CHECK_INTERVAL_SECONDS`
  below ~60 seconds for many coins at once.
- RSI/MA crossovers are lagging, well-known indicators — they don't predict
  the future, they describe what already happened. Treat alerts as "worth
  looking into," not "guaranteed signal."
