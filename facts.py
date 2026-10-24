"""
Prints the data facts needed for the report.
Run in the same folder as trades.csv:   python facts.py
"""
import pandas as pd

t = pd.read_csv("trades.csv", parse_dates=["trade_date", "disclosure_date"])
b = t[t["type"].str.startswith("buy", na=False)]
lo, hi = b["disclosure_date"].min(), b["disclosure_date"].max()

print("trades:", len(t), "| buys:", len(b))
print("politicians:", t["name"].nunique(), "| tickers:", t["ticker"].nunique())
print("disclosure range:", t["disclosure_date"].min().date(), "to", t["disclosure_date"].max().date())
print("buy range:", lo.date(), "to", hi.date(), "| months:", round((hi - lo).days / 30.4, 1))
print("holdout starts:", (lo + (hi - lo) * 0.7).date())

gap = (t["disclosure_date"] - t["trade_date"]).dt.days
print("gap days median / mean / max:", gap.median(), round(gap.mean(), 1), gap.max())

try:
    raw = pd.read_csv("trades_raw.csv")
    print("raw rows:", len(raw), "| clean rows:", len(t))
    print("first 3 raw rows (published, traded, filed_after columns):")
    print(raw.iloc[:3, [2, 3, 4]].to_string())
except Exception as e:
    print("could not read trades_raw.csv:", e)