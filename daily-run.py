import argparse
 
import pandas as pd
 
HERD_WINDOW_DAYS = 30
SMA_LEN = 20
STALE_DAYS = 5
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="report date, YYYY-MM-DD (default today)")
    args = ap.parse_args()
    target = pd.Timestamp(args.date) if args.date else pd.Timestamp.today().normalize()
 
    trades = pd.read_csv("trades.csv", parse_dates=["trade_date", "disclosure_date"])
    prices = pd.read_csv("prices.csv", parse_dates=["Date"])
    buys = trades[trades["type"].str.startswith("buy", na=False)]
    todays = buys[buys["disclosure_date"] == target]
 
    rows = []
    for tkr, g in todays.groupby("ticker"):
        window = buys[(buys["ticker"] == tkr)
                      & (buys["disclosure_date"] > target - pd.Timedelta(days=HERD_WINDOW_DAYS))
                      & (buys["disclosure_date"] <= target)]
        herd = window["name"].nunique()
        parties = "/".join(sorted(g["party"].dropna().unique()))
 
        px = prices[(prices["ticker"] == tkr) & (prices["Date"] <= target)].sort_values("Date")
        above, last_close, stale = None, None, False
        if len(px):
            last_close = round(float(px["Close"].iloc[-1]), 2)
            stale = (target - px["Date"].iloc[-1]).days > STALE_DAYS
        if len(px) >= SMA_LEN:
            above = bool(px["Close"].iloc[-1] > px["Close"].tail(SMA_LEN).mean())
 
        score = min(herd, 3) + (1 if above else 0)
        parts = [f"{herd} politician(s) bought in the last {HERD_WINDOW_DAYS} days"]
        if above is None:
            parts.append("not enough price history for the 20-day average")
        else:
            parts.append("above its 20-day average" if above else "below its 20-day average")
        if stale:
            parts.append("price data is stale, run political_updater.py")
 
        rows.append(dict(
            date=target.date(), ticker=tkr, score=score,
            politicians="; ".join(sorted(g["name"].unique())),
            parties=parties, herd_30d=herd,
            above_20d_avg=above, last_close=last_close,
            size=" / ".join(sorted(g["size"].dropna().unique())),
            comment=", ".join(parts)))
 
    cols = ["date", "ticker", "score", "politicians", "parties", "herd_30d",
            "above_20d_avg", "last_close", "size", "comment"]
    report = pd.DataFrame(rows, columns=cols)
    if len(report):
        report = report.sort_values(["score", "herd_30d"], ascending=False)
    out = f"daily_report_{target.date()}.csv"
    report.to_csv(out, index=False)
 
    if report.empty:
        print(f"No buys disclosed on {target.date()}. Wrote an empty {out}.")
        print("(No filings on weekends and holidays, or run political_updater.py first.)")
    else:
        print(report[["ticker", "score", "herd_30d", "parties", "above_20d_avg"]].to_string(index=False))
        print(f"\nwrote {out} ({len(report)} stocks)")
    print("Reminder: the backtest found no reliable edge. Use the score to rank, not to trade.")
 
 
if __name__ == "__main__":
    main()