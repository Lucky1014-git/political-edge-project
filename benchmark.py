"""
Benchmark check: compare every backtest trade to SPY over the same days.

Run after backtest.py (needs trades_backtest.csv in the same folder):
    python benchmark.py
"""
import pandas as pd


def get_spy(start, end):
    import yfinance as yf
    h = yf.Ticker("SPY").history(start=str(start.date()), end=str(end.date()), auto_adjust=True)
    h = h.reset_index()
    h["Date"] = pd.to_datetime(h["Date"]).dt.tz_localize(None)
    return h.set_index("Date")[["Open", "Close"]]


def summarize(df, keys):
    return (df.groupby(keys, observed=True)
            .agg(trades=("ret", "count"),
                 avg_ret_pct=("ret", lambda s: round(s.mean() * 100, 2)),
                 avg_spy_pct=("spy_ret", lambda s: round(s.mean() * 100, 2)),
                 avg_excess_pct=("excess", lambda s: round(s.mean() * 100, 2)),
                 pct_beat_spy=("excess", lambda s: round((s > 0).mean() * 100, 1))))


def main(spy=None):
    t = pd.read_csv("trades_backtest.csv", parse_dates=["entry_date", "exit_date"])
    if spy is None:
        spy = get_spy(t["entry_date"].min() - pd.Timedelta(days=7),
                      t["exit_date"].max() + pd.Timedelta(days=7))
    t["spy_ret"] = (spy["Close"].reindex(t["exit_date"]).values
                    / spy["Open"].reindex(t["entry_date"]).values - 1)
    t["excess"] = t["ret"] - t["spy_ret"]
    missing = t["spy_ret"].isna().sum()
    t = t.dropna(subset=["spy_ret"])
    print(f"{len(t)} trades compared to SPY ({missing} dropped for missing SPY dates)\n")

    by_variant = summarize(t, ["variant", "period"])
    print("=== Trade return vs SPY over the same windows ===")
    print(by_variant.to_string())
    by_variant.to_csv("benchmark_summary.csv")

    sig = t[t["variant"] == "signal_only"].copy()
    sig["herd_bucket"] = pd.cut(sig["herd"], [0, 1, 2, 1000], labels=["1", "2", "3+"])
    print("\n=== signal_only, excess return by herd size ===")
    print(summarize(sig, ["herd_bucket", "period"]).to_string())
    print("\n=== signal_only, excess return by party ===")
    print(summarize(sig, ["party", "period"]).to_string())


if __name__ == "__main__":
    main()