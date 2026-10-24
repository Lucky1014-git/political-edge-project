"""
Step 2: backtest congressional BUY disclosures.

Needs trades.csv and prices.csv from fetch-data.py in the same folder.
Install once:  pip install matplotlib
Run:           python backtest.py

Rules (no lookahead):
  - An "event" is a ticker plus a disclosure date with at least one BUY.
  - Entry is the first OPEN after the disclosure date (never the trade date).
  - herd = unique politicians who bought the same ticker in the 30 days up to
    and including the disclosure date.
Two variants:
  signal_only: enter next open, exit at the close of day 20.
  tech:        only enter if the last close before entry is above its 20-day
               average, exit when a close falls below the average or at day 20.
Portfolio: 10% of current account equity per trade, max 10 open positions.
Holdout: the most recent 30% of the disclosure-date range.
"""
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HOLD_DAYS = 20
SMA_LEN = 20
MAX_POSITIONS = 10
POSITION_FRAC = 0.10
HERD_WINDOW_DAYS = 30
HOLDOUT_FRAC = 0.30


def load():
    trades = pd.read_csv("trades.csv", parse_dates=["trade_date", "disclosure_date"])
    prices = pd.read_csv("prices.csv", parse_dates=["Date"])
    return trades, prices


def build_events(trades):
    buys = trades[trades["type"].str.startswith("buy", na=False)].copy()
    buys = buys.dropna(subset=["disclosure_date", "ticker"])
    events = (buys.groupby(["ticker", "disclosure_date"])
              .agg(party=("party", lambda s: s.iloc[0] if s.nunique() == 1 else "Mixed"))
              .reset_index())
    by_ticker = {t: g for t, g in buys.groupby("ticker")}
    herd = []
    for t, d in zip(events["ticker"], events["disclosure_date"]):
        g = by_ticker[t]
        w = g[(g["disclosure_date"] > d - pd.Timedelta(days=HERD_WINDOW_DAYS))
              & (g["disclosure_date"] <= d)]
        herd.append(w["name"].nunique())
    events["herd"] = herd
    return events.sort_values("disclosure_date").reset_index(drop=True)


def prep_prices(prices):
    out = {}
    for t, g in prices.groupby("ticker"):
        g = g.sort_values("Date").set_index("Date")
        g = g[~g.index.duplicated()]
        g["sma"] = g["Close"].rolling(SMA_LEN).mean()
        out[t] = g
    return out


def simulate(events, px, use_ma):
    rows = []
    last_exit = {}
    for ev in events.itertuples():
        df = px.get(ev.ticker)
        if df is None:
            continue
        idx = df.index
        pos = idx.searchsorted(ev.disclosure_date, side="right") - 1
        ei = pos + 1
        if pos < 0 or ei >= len(df):
            continue
        if use_ma:
            s = df["sma"].iloc[pos]
            if np.isnan(s) or df["Close"].iloc[pos] <= s:
                continue
        if ev.ticker in last_exit and ei <= last_exit[ev.ticker]:
            continue  # already holding this ticker
        last = min(ei + HOLD_DAYS - 1, len(df) - 1)
        xi = last
        reason = "time" if last == ei + HOLD_DAYS - 1 else "open"
        if use_ma:
            for j in range(ei, last + 1):
                sj = df["sma"].iloc[j]
                if not np.isnan(sj) and df["Close"].iloc[j] < sj:
                    xi, reason = j, "ma_cross"
                    break
        entry = df["Open"].iloc[ei]
        exit_ = df["Close"].iloc[xi]
        win = df.iloc[ei:xi + 1]
        last_exit[ev.ticker] = xi
        rows.append(dict(
            ticker=ev.ticker, disclosure_date=ev.disclosure_date,
            entry_date=idx[ei], exit_date=idx[xi], entry=entry, exit=exit_,
            ret=exit_ / entry - 1,
            mfe=win["High"].max() / entry - 1, mae=win["Low"].min() / entry - 1,
            hold=xi - ei + 1, reason=reason, herd=ev.herd, party=ev.party))
    return pd.DataFrame(rows)


def portfolio(tr, closes):
    days = closes.index[(closes.index >= tr["entry_date"].min())
                        & (closes.index <= tr["exit_date"].max())]
    entries = {d: g for d, g in tr.groupby("entry_date")}
    exits = {d: g for d, g in tr.groupby("exit_date")}
    cash, equity = 1.0, 1.0
    open_pos, out, skipped = {}, [], 0
    for d in days:
        if d in entries:
            for i, r in entries[d].iterrows():
                size = min(POSITION_FRAC * equity, cash)
                if len(open_pos) >= MAX_POSITIONS or size <= 0:
                    skipped += 1
                    continue
                open_pos[i] = (r["ticker"], size / r["entry"])
                cash -= size
        if d in exits:
            for i, r in exits[d].iterrows():
                if i in open_pos:
                    _, sh = open_pos.pop(i)
                    cash += sh * r["exit"]
        invested = sum(sh * closes.at[d, t] for t, sh in open_pos.values())
        equity = cash + invested
        out.append((d, equity, invested))
    eq = pd.DataFrame(out, columns=["date", "equity", "invested"]).set_index("date")
    return eq, skipped


def period_stats(name, period, tr, eq, start, end):
    t = tr[(tr["entry_date"] >= start) & (tr["entry_date"] < end)]
    e = eq[(eq.index >= start) & (eq.index < end)]
    if len(t) == 0 or len(e) < 2:
        return dict(variant=name, period=period, trades=len(t))
    total = e["equity"].iloc[-1] / e["equity"].iloc[0] - 1
    years = (e.index[-1] - e.index[0]).days / 365.25
    cagr = (1 + total) ** (1 / years) - 1 if years > 0.05 else np.nan
    return dict(variant=name, period=period, trades=len(t),
                total_return=round(total * 100, 2),
                cagr_pct=round(cagr * 100, 1) if not np.isnan(cagr) else None,
                avg_trade_pct=round(t["ret"].mean() * 100, 2),
                win_rate_pct=round((t["ret"] > 0).mean() * 100, 1),
                pct_invested=round((e["invested"] / e["equity"]).mean() * 100, 1),
                avg_mfe_pct=round(t["mfe"].mean() * 100, 2),
                avg_mae_pct=round(t["mae"].mean() * 100, 2))


def main():
    trades, prices = load()
    events = build_events(trades)
    px = prep_prices(prices)
    closes = prices.pivot_table(index="Date", columns="ticker", values="Close").sort_index().ffill()

    lo, hi = events["disclosure_date"].min(), events["disclosure_date"].max()
    cutoff = lo + (hi - lo) * (1 - HOLDOUT_FRAC)
    far = hi + pd.Timedelta(days=365)
    print(f"{len(events)} buy events, disclosure dates {lo.date()} to {hi.date()}")
    print(f"holdout starts {cutoff.date()} (last {int(HOLDOUT_FRAC * 100)}% of the range)\n")

    results, curves, all_trades = [], {}, []
    for name, use_ma in [("signal_only", False), ("tech", True)]:
        tr = simulate(events, px, use_ma)
        if tr.empty:
            print(name, ": no trades"); continue
        tr = tr.sort_values("entry_date").reset_index(drop=True)
        eq, skipped = portfolio(tr, closes)
        curves[name] = eq
        tr["variant"] = name
        tr["period"] = np.where(tr["entry_date"] >= cutoff, "holdout", "in_sample")
        all_trades.append(tr)
        print(f"{name}: {len(tr)} trades simulated, {skipped} skipped by the 10-position cap")
        results.append(period_stats(name, "in_sample", tr, eq, lo, cutoff))
        results.append(period_stats(name, "holdout", tr, eq, cutoff, far))

    summary = pd.DataFrame(results)
    print("\n=== Summary ===")
    print(summary.to_string(index=False))
    summary.to_csv("stats_summary.csv", index=False)

    if all_trades:
        allt = pd.concat(all_trades)
        allt.to_csv("trades_backtest.csv", index=False)
        sig = allt[allt["variant"] == "signal_only"].copy()
        sig["herd_bucket"] = pd.cut(sig["herd"], [0, 1, 2, 1000], labels=["1", "2", "3+"])
        for col in ["herd_bucket", "party"]:
            g = (sig.groupby([col, "period"], observed=True)["ret"]
                 .agg(trades="count", avg_ret_pct=lambda s: round(s.mean() * 100, 2),
                      win_rate_pct=lambda s: round((s > 0).mean() * 100, 1)))
            print(f"\n=== signal_only by {col} ===")
            print(g.to_string())

    fig, ax = plt.subplots(figsize=(10, 5))
    for name, eq in curves.items():
        ax.plot(eq.index, eq["equity"], label=name)
    ax.axvline(cutoff, color="red", linestyle="--")
    ax.axvspan(cutoff, max(e.index.max() for e in curves.values()), alpha=0.1, color="red",
               label="holdout")
    ax.set_title("Equity curves (start = 1.0)")
    ax.legend()
    fig.tight_layout()
    fig.savefig("equity_curve.png", dpi=150)
    print("\nsaved equity_curve.png, stats_summary.csv, trades_backtest.csv")


if __name__ == "__main__":
    main()