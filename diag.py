"""
Find which positions caused the one-day jump in the signal_only equity curve
right after the holdout starts.

Run in the same folder as trades_backtest.csv and prices.csv:   python diag.py
"""
import pandas as pd

t = pd.read_csv("trades_backtest.csv", parse_dates=["entry_date", "exit_date"])
t = t[t["variant"] == "signal_only"]
p = pd.read_csv("prices.csv", parse_dates=["Date"])
c = p.pivot_table(index="Date", columns="ticker", values="Close").sort_index().ffill()

start, end = pd.Timestamp("2026-08-24"), pd.Timestamp("2026-08-31")
days = c.index[(c.index >= start) & (c.index <= end)]

for prev, d in zip(days[:-1], days[1:]):
    held = t[(t["entry_date"] <= prev) & (t["exit_date"] >= d)].copy()
    held["day_move_pct"] = [round((c.at[d, k] / c.at[prev, k] - 1) * 100, 1) for k in held["ticker"]]
    print(f"\n{prev.date()} -> {d.date()}: {len(held)} candidate positions, "
          f"average one-day move {held['day_move_pct'].mean():.2f}%")
    top = held.reindex(held["day_move_pct"].abs().sort_values(ascending=False).index).head(5)
    print(top[["ticker", "entry_date", "exit_date", "day_move_pct"]].to_string(index=False))