"""
Strategy Backtester
--------------------
Tests the exact RSI + moving-average strategy used in bot.py / scanner.py
against real historical price data, so you can see whether it would have
actually made money BEFORE trusting it with real trades.

Simulates a simple long-only strategy:
  - BUY when RSI < oversold threshold OR a golden cross happens
  - SELL (close position) when RSI > overbought threshold OR a death cross happens
  - Only ever holds one position at a time, all-in / all-out (no leverage)

Compares the strategy's return against simple buy-and-hold over the same
period, and reports win rate, number of trades, and max drawdown.

This is a research tool, not a promise the strategy will work in the
future. Past performance does not guarantee future results — markets
change, and a strategy that worked for one coin/period can fail on
another. Trading fees are included by default (0.1%, Binance's standard
spot fee) but slippage is not modeled.

USAGE:
    python backtest.py                  # backtests BTCUSDT by default
    python backtest.py ETHUSDT          # backtest a different coin
    python backtest.py ETHUSDT 90       # backtest over last 90 days
"""

import sys
import time
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

from bot import compute_rsi, RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT, MA_SHORT, MA_LONG, INTERVAL

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
TRADING_FEE_PCT = 0.001  # 0.1% per trade, Binance spot default


def fetch_historical_klines(symbol: str, interval: str, days: int) -> pd.DataFrame:
    """Fetch up to `days` worth of historical candles, paginating as needed
    (Binance caps each request at 1000 candles)."""
    end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_time = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

    all_rows = []
    cursor = start_time

    while cursor < end_time:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": cursor,
            "limit": 1000,
        }
        resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=15)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        all_rows.extend(rows)
        cursor = rows[-1][6] + 1  # close_time of last candle + 1ms
        if len(rows) < 1000:
            break
        time.sleep(0.2)  # be polite to the API

    df = pd.DataFrame(all_rows, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["close"] = df["close"].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df.drop_duplicates(subset="open_time").reset_index(drop=True)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rsi"] = compute_rsi(df["close"], RSI_PERIOD)
    df["ma_short"] = df["close"].rolling(MA_SHORT).mean()
    df["ma_long"] = df["close"].rolling(MA_LONG).mean()
    return df


def run_backtest(df: pd.DataFrame, initial_capital: float = 1000.0) -> dict:
    """Simulate the strategy bar-by-bar. Returns trade log + summary metrics."""
    cash = initial_capital
    coin_held = 0.0
    position_open = False
    entry_price = 0.0

    trades = []
    equity_curve = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]

        if pd.isna(row["rsi"]) or pd.isna(row["ma_long"]):
            equity_curve.append(cash + coin_held * row["close"])
            continue

        golden_cross = prev["ma_short"] <= prev["ma_long"] and row["ma_short"] > row["ma_long"]
        death_cross = prev["ma_short"] >= prev["ma_long"] and row["ma_short"] < row["ma_long"]

        buy_signal = row["rsi"] < RSI_OVERSOLD or golden_cross
        sell_signal = row["rsi"] > RSI_OVERBOUGHT or death_cross

        if not position_open and buy_signal:
            coin_held = (cash * (1 - TRADING_FEE_PCT)) / row["close"]
            cash = 0.0
            entry_price = row["close"]
            position_open = True
            trades.append({
                "type": "BUY", "time": row["open_time"], "price": row["close"]
            })

        elif position_open and sell_signal:
            cash = coin_held * row["close"] * (1 - TRADING_FEE_PCT)
            coin_held = 0.0
            trades.append({
                "type": "SELL", "time": row["open_time"], "price": row["close"],
                "return_pct": (row["close"] / entry_price - 1) * 100
            })
            position_open = False

        equity_curve.append(cash + coin_held * row["close"])

    # Close any open position at the final price for fair comparison
    final_price = df.iloc[-1]["close"]
    final_equity = cash + coin_held * final_price

    buy_hold_equity = initial_capital * (final_price / df.iloc[0]["close"])

    completed_trades = [t for t in trades if t["type"] == "SELL"]
    wins = [t for t in completed_trades if t["return_pct"] > 0]
    win_rate = (len(wins) / len(completed_trades) * 100) if completed_trades else 0.0

    # Max drawdown on the equity curve
    equity_series = pd.Series(equity_curve)
    running_max = equity_series.cummax()
    drawdown = (equity_series - running_max) / running_max
    max_drawdown_pct = drawdown.min() * 100 if len(drawdown) else 0.0

    return {
        "initial_capital": initial_capital,
        "final_equity": final_equity,
        "strategy_return_pct": (final_equity / initial_capital - 1) * 100,
        "buy_hold_equity": buy_hold_equity,
        "buy_hold_return_pct": (buy_hold_equity / initial_capital - 1) * 100,
        "num_trades": len(completed_trades),
        "win_rate_pct": win_rate,
        "max_drawdown_pct": max_drawdown_pct,
        "trades": trades,
        "position_still_open": position_open,
    }


def print_report(symbol: str, days: int, results: dict):
    print("=" * 55)
    print(f"BACKTEST REPORT — {symbol} — last {days} days ({INTERVAL} candles)")
    print("=" * 55)
    print(f"Initial capital:      ${results['initial_capital']:,.2f}")
    print(f"Strategy final value: ${results['final_equity']:,.2f}  ({results['strategy_return_pct']:+.2f}%)")
    print(f"Buy & hold value:     ${results['buy_hold_equity']:,.2f}  ({results['buy_hold_return_pct']:+.2f}%)")
    print("-" * 55)
    print(f"Number of completed trades: {results['num_trades']}")
    print(f"Win rate:                   {results['win_rate_pct']:.1f}%")
    print(f"Max drawdown:                {results['max_drawdown_pct']:.2f}%")
    if results["position_still_open"]:
        print("Note: strategy still holding an open position at end of period.")
    print("=" * 55)

    if results["strategy_return_pct"] > results["buy_hold_return_pct"]:
        print("Strategy BEAT buy-and-hold over this period.")
    else:
        print("Strategy UNDERPERFORMED buy-and-hold over this period.")
    print("Remember: past performance on this one coin/period does not")
    print("guarantee future results. Test across multiple coins and time")
    print("periods before trusting this with real money.")


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 180

    print(f"Fetching {days} days of {INTERVAL} data for {symbol}...")
    df = fetch_historical_klines(symbol, INTERVAL, days)
    print(f"Fetched {len(df)} candles.")

    if len(df) < MA_LONG + 10:
        print("Not enough data to backtest reliably. Try a longer period or different interval.")
        return

    df = add_indicators(df)
    results = run_backtest(df)
    print_report(symbol, days, results)

    # Save trade log for closer inspection
    trades_df = pd.DataFrame(results["trades"])
    out_path = f"backtest_trades_{symbol}.csv"
    trades_df.to_csv(out_path, index=False)
    print(f"\nFull trade log saved to {out_path}")


if __name__ == "__main__":
    main()
