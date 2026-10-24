"""
Step 1: download congressional trades (Capitol Trades) and daily prices (Yahoo Finance).

Install once:   pip install requests beautifulsoup4 pandas yfinance
Run:            python fetch_data.py

Outputs (in the same folder):
    trades_raw.csv   raw table cells exactly as scraped (for debugging)
    trades.csv       cleaned trades, one row per trade
    prices.csv       daily OHLCV for every ticker in trades.csv
"""
import re
import time

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

URL = "https://www.capitoltrades.com/trades"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
MAX_PAGES = 60          # safety cap; the loop stops earlier when pages run out
PAGE_SIZE = 96
PRICE_LOOKBACK_DAYS = 60  # extra history before the first trade, for the 20-day average

COLS = ["politician", "issuer", "published", "traded", "filed_after",
        "owner", "type", "size", "price"]


def scrape_trades():
    rows = []
    for page in range(1, MAX_PAGES + 1):
        resp = requests.get(URL, params={"page": page, "pageSize": PAGE_SIZE},
                            headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f"page {page}: HTTP {resp.status_code}, stopping")
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        trs = soup.select("table tbody tr")
        if not trs:
            print(f"page {page}: no rows, done")
            break
        for tr in trs:
            cells = [td.get_text(" | ", strip=True) for td in tr.find_all("td")]
            if cells:
                rows.append(cells)
        print(f"page {page}: {len(trs)} rows (total {len(rows)})")
        time.sleep(1.5)  # be polite to the site
    return rows


def to_date(text):
    text = str(text).replace(" | ", " ")
    return pd.to_datetime(text, errors="coerce")


def clean(rows):
    raw = pd.DataFrame(rows)
    raw.to_csv("trades_raw.csv", index=False)
    if raw.shape[1] < len(COLS):
        raise SystemExit(f"Expected {len(COLS)} columns but got {raw.shape[1]}. "
                         "Open trades_raw.csv and paste me the first 3 rows.")
    df = raw.iloc[:, :len(COLS)].copy()
    df.columns = COLS

    # Politician cell looks like: "Nancy Pelosi | Democrat | House | CA"
    pol = df["politician"].str.split(r" \| ", expand=True)
    df["name"] = pol[0]
    df["party"] = pol[1] if pol.shape[1] > 1 else None
    df["chamber"] = pol[2] if pol.shape[1] > 2 else None

    # Issuer cell looks like: "Bloom Energy Corp | BE:US"
    df["ticker"] = df["issuer"].str.extract(r"\b([A-Z][A-Z0-9.\-]*):US")[0]

    df["disclosure_date"] = df["published"].apply(to_date)
    df["trade_date"] = df["traded"].apply(to_date)
    df["type"] = df["type"].str.lower().str.strip()

    out = df[["name", "party", "chamber", "ticker", "type",
              "trade_date", "disclosure_date", "size", "owner"]]
    before = len(out)
    out = out.dropna(subset=["ticker", "disclosure_date"]).drop_duplicates()
    print(f"kept {len(out)} of {before} rows after dropping missing ticker/date")
    return out


def fetch_prices(trades):
    tickers = sorted(trades["ticker"].unique())
    start = (trades["trade_date"].min() - pd.Timedelta(days=PRICE_LOOKBACK_DAYS)).date()
    frames = []
    for i, t in enumerate(tickers, 1):
        try:
            h = yf.Ticker(t).history(start=str(start), auto_adjust=True)
            if h.empty:
                print(f"[{i}/{len(tickers)}] {t}: no data")
                continue
            h = h.reset_index()[["Date", "Open", "High", "Low", "Close", "Volume"]]
            h["Date"] = pd.to_datetime(h["Date"]).dt.tz_localize(None)
            h.insert(0, "ticker", t)
            frames.append(h)
        except Exception as e:
            print(f"[{i}/{len(tickers)}] {t}: error {e}")
        time.sleep(0.2)
    prices = pd.concat(frames, ignore_index=True)
    prices.to_csv("prices.csv", index=False)
    print(f"saved prices for {prices['ticker'].nunique()} tickers")


if __name__ == "__main__":
    rows = scrape_trades()
    trades = clean(rows)
    trades.to_csv("trades.csv", index=False)
    print(trades.head(10).to_string())
    print("date range:", trades["disclosure_date"].min(), "to", trades["disclosure_date"].max())
    fetch_prices(trades)