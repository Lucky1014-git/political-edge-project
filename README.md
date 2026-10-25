
# political-edge-project

Tests whether buying a stock the day after a member of Congress discloses buying it produces returns that hold up on unseen data. Includes a daily updater and a daily report.

## Setup (once)

You need Python 3 and an internet connection. In a terminal, from this folder:

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

On Windows, activate with `venv\Scripts\activate` instead of the `source` line.

Your prompt should start with `(venv)`. Run every script below from the terminal with `(venv)` showing, not from an editor's Run button, which can use a different Python without these packages.

## Files

| File | What it does |
|---|---|
| `fetch-data.py` | Scrapes trades from Capitol Trades and downloads daily prices from Yahoo Finance. Writes `trades.csv` and `prices.csv`. |
| `backtest.py` | Runs both trading rules with a holdout split. Writes `stats_summary.csv`, `trades_backtest.csv` and `equity_curve.png`. |
| `benchmark.py` | Compares every backtest trade with SPY over the same days. Writes `benchmark_summary.csv`. |
| `facts.py` | Prints the data counts used in the report. |
| `political-updater.py` | Adds new trades and new prices to the database. Run daily. |
| `daily-run.py` | Writes `daily_report_YYYY-MM-DD.csv` for the stocks disclosed that day. |

## Run order

First time:

```
python fetch-data.py       # about 15 minutes, mostly the price download
python backtest.py
python benchmark.py
```

Every weekday morning:

```
python political-updater.py --quick && python daily-run.py
```

The `&&` means the report only runs if the updater finished without an error. `--quick` only refreshes prices for tickers in newly added trades. Run `python political-updater.py` without it about once a week to refresh every ticker.

To run the report for a past day: `python daily-run.py --date 2026-10-09`. There are no filings on weekends and holidays, so those days give an empty report.

## Notes

- `prices.csv` is large, so it is not stored in this repository. Running `fetch-data.py` creates it.
- A fresh run uses newer data than the report did, so numbers will differ from the report. The `trades.csv` in the first commit of this repository is the data the report was built on.
- The Daily Run score is 1 to 3 points for how many politicians bought the stock in the last 30 days, plus 1 if it is above its 20-day average. The backtest found no reliable edge, so the score ranks the day's stocks and is not a buy signal.
- If a script says `No module named 'yfinance'`, the virtual environment is not active. Run `source venv/bin/activate` and try again.
- The scripts read a public website. Keep the pauses between requests in place.
- Report Link: https://docs.google.com/document/d/1EcP3JyPBOhIR4bqRza0_4qel2q3wYbijaKcwOkk4Tyg/edit?usp=sharing
