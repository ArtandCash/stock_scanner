import streamlit as st
import yfinance as yf
import finnhub
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------- PAGE CONFIG ----------------------
st.set_page_config(
    page_title="US Momentum Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------- DARK THEME CSS (inspired by your terminal image) ----------------------
st.markdown("""
<style>
    /* Main background - deep dark blue/black */
    .stApp {
        background-color: #0b1220;
        color: #e0e6ed;
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #0f172a;
        border-right: 1px solid #1e293b;
    }
    
    /* Headers */
    h1, h2, h3, h4 {
        color: #f1f5f9 !important;
    }
    
    /* Metric cards */
    div[data-testid="stMetric"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 12px;
    }
    
    /* Buttons */
    .stButton > button {
        background-color: #3b82f6;
        color: white;
        border-radius: 6px;
        border: none;
        font-weight: 600;
    }
    .stButton > button:hover {
        background-color: #2563eb;
        color: white;
    }
    
    /* Dataframes / tables */
    .stDataFrame {
        background-color: #0f172a;
    }
    
    /* Custom panel style */
    .panel {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    
    /* Hide Streamlit branding a bit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ---------------------- CONFIG ----------------------
FINNHUB_API_KEY = st.secrets.get("FINNHUB_API_KEY", "d9s6fc1r01qoo7o6rmngd9s6fc1r01qoo7o6rmo0")
MAX_CANDIDATES = 30
NEWS_LOOKBACK_DAYS = 2
PRICE_MIN, PRICE_MAX = 2.0, 20.0
REL_VOL_THRESHOLD = 5.0
FLOAT_THRESHOLD = 20_000_000

# ---------------------- HELPERS ----------------------
def get_seed_tickers():
    tickers = set()
    try:
        gainers = yf.screen("day_gainers", count=40)
        for q in gainers.get("quotes", []):
            sym = q.get("symbol")
            pct = q.get("regularMarketChangePercent") or 0
            price = q.get("regularMarketPrice") or 0
            if sym and pct >= 5 and 1 <= price <= 40:
                tickers.add(sym)
    except Exception:
        pass

    try:
        actives = yf.screen("most_actives", count=25)
        for q in actives.get("quotes", []):
            sym = q.get("symbol")
            price = q.get("regularMarketPrice") or 0
            if sym and 1 <= price <= 40:
                tickers.add(sym)
    except Exception:
        pass

    return list(tickers)[:MAX_CANDIDATES]


def fetch_one(symbol, client):
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        pct_change = info.get("regularMarketChangePercent")
        if price is None or pct_change is None:
            return None

        current_vol = info.get("regularMarketVolume") or 0
        avg_vol = info.get("averageVolume") or info.get("averageDailyVolume10Day")
        if not avg_vol:
            hist = t.history(period="1mo")
            avg_vol = hist["Volume"].tail(20).mean() if not hist.empty else None

        rel_vol = (current_vol / avg_vol) if avg_vol and avg_vol > 0 else None

        float_shares = info.get("floatShares") or info.get("sharesOutstanding")
        float_m = float_shares / 1_000_000 if float_shares else None

        has_news = False
        headline = ""
        news_list = []
        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=NEWS_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
            news = client.company_news(symbol, _from=start, to=end)
            if news:
                has_news = True
                headline = news[0].get("headline", "")[:90]
                news_list = [n.get("headline", "")[:100] for n in news[:5]]
        except Exception:
            pass

        sector = info.get("sector") or "—"
        market_cap = info.get("marketCap")
        market_cap_m = round(market_cap / 1_000_000, 1) if market_cap else None

        c1 = pct_change >= 10
        c2 = rel_vol is not None and rel_vol >= REL_VOL_THRESHOLD
        c3 = has_news
        c4 = PRICE_MIN <= price <= PRICE_MAX
        c5 = float_m is not None and float_m < 20

        score = sum([c1, c2, c3, c4, c5])

        return {
            "Symbol": symbol,
            "Price": round(price, 2),
            "% Change": round(pct_change, 2),
            "Rel Vol": round(rel_vol, 1) if rel_vol else None,
            "Float (M)": round(float_m, 2) if float_m else None,
            "Volume": current_vol,
            "Avg Vol": int(avg_vol) if avg_vol else None,
            "Market Cap (M)": market_cap_m,
            "Sector": sector,
            "News": "Yes" if has_news else "No",
            "Headline": headline,
            "News List": news_list,
            "C1 Up10%": c1,
            "C2 RVol5x": c2,
            "C3 News": c3,
            "C4 $2-20": c4,
            "C5 Float<20M": c5,
            "Score": score,
        }
    except Exception:
        return None
