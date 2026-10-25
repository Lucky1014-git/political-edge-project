import argparse
import os
import time
 
import pandas as pd
 
URL = "https://www.capitoltrades.com/trades"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
PAGE_SIZE = 96
MAX_PAGES = 10
PRICE_LOOKBACK_DAYS = 60
SKIP_FILE = "no_price_tickers.txt"
 
COLS = ["politician", "issuer", "published", "traded", "filed_after",
        "owner", "type", "size", "price"]
OUT_COLS = ["name", "party", "chamber", "ticker", "type",
            "trade_date", "disclosure_date", "size", "owner"]
KEY = ["name", "ticker", "type", "trade_date", "disclosure_date", "size", "owner"]
 
 
def scrape_page(page):
    import requests
    from bs4 import BeautifulSoup
    resp = requests.get(URL, params={"page": page, "pageSize": PAGE_SIZE},
                        headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"page {page}: HTTP {resp.status_code}")
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    for tr in soup.select("table tbody tr"):
        cells = [td.get_text(" | ", strip=True) for td in tr.find_all("td")]
        if cells:
            rows.append(cells)
    return rows
 
 
def to_date(text, today):
    s = str(text).replace(" | ", " ").strip()
    low = s.lower()
    if "today" in low:
        return pd.Timestamp(today)
    if "yesterday" in low:
        return pd.Timestamp(today) - pd.Timedelta(days=1)
    return pd.to_datetime(s, errors="coerce")
 
 
def clean(rows, today):
    if not rows:
        return pd.DataFrame(columns=OUT_COLS)
    raw = pd.DataFrame(rows)
    if raw.shape[1] < len(COLS):
        raise SystemExit(f"Expected {len(COLS)} columns but got {raw.shape[1]}. "
                         "The site layout may have changed.")
    df = raw.iloc[:, :len(COLS)].copy()
    df.columns = COLS
    pol = df["politician"].str.split(r" \| ", expand=True, regex=True)
    df["name"] = pol[0]
    df["party"] = pol[1] if pol.shape[1] > 1 else None
    df["chamber"] = pol[2] if pol.shape[1] > 2 else None
    df["ticker"] = df["issuer"].str.extract(r"\b([A-Z][A-Z0-9.\-]*):US")[0]
    df["disclosure_date"] = df["published"].apply(lambda x: to_date(x, today))
    df["trade_date"] = df["traded"].apply(lambda x: to_date(x, today))
    df["type"] = df["type"].str.lower().str.strip()
    out = df[OUT_COLS]
    return out.dropna(subset=["ticker", "disclosure_date"]).drop_duplicates()
 
 
def make_key(df):
    if df.empty:
        return pd.Series([], dtype=str)
    d = df.copy()
    for c in ["trade_date", "disclosure_date"]:
        d[c] = pd.to_datetime(d[c]).dt.strftime("%Y-%m-%d")
    return d[KEY].fillna("").astype(str).agg("|".join, axis=1)
 
 
def update_trades(existing, today):
    known = set(make_key(existing))
    new_frames = []
    for page in range(1, MAX_PAGES + 1):
        rows = scrape_page(page)
        if not rows:
            break
        page_df = clean(rows, today)
        fresh = page_df[~make_key(page_df).isin(known)] if len(page_df) else page_df
        print(f"page {page}: {len(rows)} rows, {len(fresh)} new")
        if len(fresh) == 0:
            break  # pages are newest first, so everything after this is already stored
        new_frames.append(fresh)
        known |= set(make_key(fresh))
        time.sleep(1.5)
    new = pd.concat(new_frames, ignore_index=True) if new_frames else pd.DataFrame(columns=OUT_COLS)
    combined = pd.concat([existing, new], ignore_index=True)
    combined["_k"] = make_key(combined)
    combined = (combined.drop_duplicates("_k").drop(columns="_k")
                .sort_values("disclosure_date").reset_index(drop=True))
    return combined, new
 
 
def fetch_history(ticker, start):
    import yfinance as yf
    h = yf.Ticker(ticker).history(start=str(start), auto_adjust=True)
    if h.empty:
        return None
    h = h.reset_index()[["Date", "Open", "High", "Low", "Close", "Volume"]]
    h["Date"] = pd.to_datetime(h["Date"]).dt.tz_localize(None)
    h.insert(0, "ticker", ticker)
    return h
 
 
def update_prices(trades, prices, tickers, today):
    skip = set(open(SKIP_FILE).read().split()) if os.path.exists(SKIP_FILE) else set()
    last = prices.groupby("ticker")["Date"].max()
    first_trade = trades.groupby("ticker")["trade_date"].min()
    frames, updated = [], 0
    for i, t in enumerate(sorted(tickers), 1):
        if t in skip:
            continue
        if t in last.index:
            start = last[t] + pd.Timedelta(days=1)
        else:
            start = first_trade[t] - pd.Timedelta(days=PRICE_LOOKBACK_DAYS)
        if pd.isna(start) or start.date() > today:
            continue
        try:
            h = fetch_history(t, start.date())
        except Exception as e:
            print(f"{t}: error {e}")
            continue
        if h is None:
            if t not in last.index:
                skip.add(t)
            continue
        frames.append(h)
        updated += 1
        time.sleep(0.2)
    if frames:
        prices = pd.concat([prices] + frames, ignore_index=True)
        prices = (prices.drop_duplicates(["ticker", "Date"], keep="last")
                  .sort_values(["ticker", "Date"]).reset_index(drop=True))
    with open(SKIP_FILE, "w") as f:
        f.write("\n".join(sorted(skip)))
    return prices, updated
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="only refresh prices for tickers in newly added trades")
    args = ap.parse_args()
    today = pd.Timestamp.today().date()
 
    existing = pd.read_csv("trades.csv", parse_dates=["trade_date", "disclosure_date"])
    prices = pd.read_csv("prices.csv", parse_dates=["Date"])
 
    trades, new = update_trades(existing, today)
    trades.to_csv("trades.csv", index=False)
    print(f"\nadded {len(new)} new trades ({len(trades)} total)")
    if len(new):
        print("newest disclosure date:", trades["disclosure_date"].max().date())
 
    tickers = set(new["ticker"]) if args.quick else set(trades["ticker"])
    prices, updated = update_prices(trades, prices, tickers, today)
    prices.to_csv("prices.csv", index=False)
    print(f"prices updated for {updated} tickers, latest price date {prices['Date'].max().date()}")
 
 
if __name__ == "__main__":
    main()
 