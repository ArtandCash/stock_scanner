"""
US Stock Scanner - 5 Criteria Ranked Table
Criteria (equal weight):
1. Price up >= 10% today
2. Relative Volume >= 5x
3. Recent news present (Finnhub)
4. Price between $2 and $20
5. Float < 20 million shares
"""

import streamlit as st
import yfinance as yf
import finnhub
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# ---------------------- CONFIG ----------------------
FINNHUB_API_KEY = st.secrets.get("FINNHUB_API_KEY", "d9s6fc1r01qoo7o6rmngd9s6fc1r01qoo7o6rmo0")
MAX_CANDIDATES = 40          # Limit to control rate limits
NEWS_LOOKBACK_DAYS = 2
MIN_PCT_CHANGE_SEED = 5.0    # Seed filter from gainers
PRICE_MIN, PRICE_MAX = 2.0, 20.0
REL_VOL_THRESHOLD = 5.0
FLOAT_THRESHOLD = 20_000_000
CACHE_TTL = 55               # seconds

st.set_page_config(
    page_title="US Momentum Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------- HELPERS ----------------------
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_seed_tickers():
    """Get unique candidates from day_gainers + most_actives."""
    tickers = set()
    try:
        gainers = yf.screen("day_gainers", count=50)
        for q in gainers.get("quotes", []):
            sym = q.get("symbol")
            pct = q.get("regularMarketChangePercent") or 0
            price = q.get("regularMarketPrice") or 0
            if sym and pct >= MIN_PCT_CHANGE_SEED and PRICE_MIN * 0.5 <= price <= PRICE_MAX * 2:
                tickers.add(sym)
    except Exception as e:
        st.warning(f"Gainers screen failed: {e}")

    try:
        actives = yf.screen("most_actives", count=30)
        for q in actives.get("quotes", []):
            sym = q.get("symbol")
            price = q.get("regularMarketPrice") or 0
            if sym and PRICE_MIN * 0.5 <= price <= PRICE_MAX * 2:
                tickers.add(sym)
    except Exception as e:
        st.warning(f"Actives screen failed: {e}")

    return list(tickers)[:MAX_CANDIDATES]


def fetch_ticker_data(symbol: str, finnhub_client) -> dict | None:
    """Fetch all metrics for one ticker. Returns dict or None on failure."""
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}

        # Price & change
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
        pct_change = info.get("regularMarketChangePercent")
        if pct_change is None and price and prev_close and prev_close > 0:
            pct_change = ((price - prev_close) / prev_close) * 100

        if price is None or pct_change is None:
            return None

        # Volume & Relative Volume
        current_vol = info.get("regularMarketVolume") or info.get("volume") or 0
        avg_vol = (
            info.get("averageVolume")
            or info.get("averageDailyVolume10Day")
            or info.get("averageVolume10days")
        )
        if not avg_vol or avg_vol == 0:
            # Fallback: compute from history
            hist = t.history(period="1mo", auto_adjust=True)
            if not hist.empty and len(hist) >= 5:
                avg_vol = hist["Volume"].tail(20).mean()
            else:
                avg_vol = None

        rel_vol = (current_vol / avg_vol) if avg_vol and avg_vol > 0 else None

        # Float
        float_shares = info.get("floatShares")
        shares_out = info.get("sharesOutstanding")
        float_m = None
        if float_shares and float_shares > 0:
            float_m = float_shares / 1_000_000
        elif shares_out and shares_out > 0:
            float_m = shares_out / 1_000_000  # fallback proxy

        # News via Finnhub
        has_news = False
        news_headline = ""
        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=NEWS_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
            news = finnhub_client.company_news(symbol, _from=start, to=end)
            if news and len(news) > 0:
                has_news = True
                news_headline = news[0].get("headline", "")[:90]
        except Exception:
            # Fallback to yfinance news
            try:
                yf_news = t.news or []
                if yf_news:
                    has_news = True
                    news_headline = yf_news[0].get("title", "")[:90]
            except Exception:
                pass

        # Criteria
        c1 = pct_change >= 10.0
        c2 = rel_vol is not None and rel_vol >= REL_VOL_THRESHOLD
        c3 = has_news
        c4 = PRICE_MIN <= price <= PRICE_MAX
        c5 = float_m is not None and float_m < (FLOAT_THRESHOLD / 1_000_000)

        score = sum([c1, c2, c3, c4, c5])

        return {
            "Symbol": symbol,
            "Price": round(price, 2),
            "% Change": round(pct_change, 2),
            "Rel Vol": round(rel_vol, 2) if rel_vol else None,
            "Float (M)": round(float_m, 2) if float_m else None,
            "News": "Yes" if has_news else "No",
            "Headline": news_headline,
            "C1 Up10%": c1,
            "C2 RVol5x": c2,
            "C3 News": c3,
            "C4 $2-20": c4,
            "C5 Float<20M": c5,
            "Score": score,
            "Volume": current_vol,
            "Avg Vol": int(avg_vol) if avg_vol else None,
        }
    except Exception:
        return None


@st.cache_data(ttl=CACHE_TTL, show_spinner="Scanning market…")
def run_scan(_api_key: str):
    """Main scan function. Cached."""
    client = finnhub.Client(api_key=_api_key)
    seeds = get_seed_tickers()
    if not seeds:
        return pd.DataFrame()

    results = []
    # Parallel fetch (keep concurrency modest for free tiers)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_ticker_data, sym, client): sym for sym in seeds}
        for future in as_completed(futures):
            data = future.result()
            if data:
                results.append(data)

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    # Rank: Score desc, then % Change desc
    df = df.sort_values(by=["Score", "% Change"], ascending=[False, False]).reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))
    return df


def style_dataframe(df: pd.DataFrame):
    """Apply visual styling."""
    def highlight_criteria(val):
        if val is True:
            return "background-color: #d4edda; color: #155724; font-weight: bold"
        if val is False:
            return "background-color: #f8d7da; color: #721c24"
        return ""

    def highlight_score(val):
        if val >= 4:
            return "background-color: #28a745; color: white; font-weight: bold"
        if val == 3:
            return "background