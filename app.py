import streamlit as st
import yfinance as yf
import finnhub
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    page_title="US Momentum Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- DARK THEME + WHITE TEXT ----------
st.markdown("""
<style>
    /* Main background */
    .stApp {
        background-color: #0b1220 !important;
        color: #f1f5f9 !important;
    }

    /* Force all main text to be light */
    .stApp p, .stApp span, .stApp label, .stApp div, .stApp li {
        color: #f1f5f9 !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #0f172a !important;
        border-right: 1px solid #1e293b;
    }
    section[data-testid="stSidebar"] * {
        color: #f1f5f9 !important;
    }

    /* Headers */
    h1, h2, h3, h4, h5, h6 {
        color: #f1f5f9 !important;
    }

    /* Metric cards */
    div[data-testid="stMetric"] {
        background-color: #1e293b !important;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 12px;
    }
    div[data-testid="stMetric"] label, div[data-testid="stMetric"] div {
        color: #f1f5f9 !important;
    }

    /* Buttons */
    .stButton > button {
        background-color: #3b82f6 !important;
        color: white !important;
        border-radius: 6px;
        border: none;
        font-weight: 600;
    }
    .stButton > button:hover {
        background-color: #2563eb !important;
        color: white !important;
    }

    /* Dataframe / table text */
    .stDataFrame, .stDataFrame * {
        color: #e0e6ed !important;
    }

    /* Selectbox and other widgets */
    .stSelectbox label, .stSlider label {
        color: #f1f5f9 !important;
    }
</style>
""", unsafe_allow_html=True)

FINNHUB_API_KEY = st.secrets.get("FINNHUB_API_KEY", "d9s6fc1r01qoo7o6rmngd9s6fc1r01qoo7o6rmo0")
MAX_CANDIDATES = 25
NEWS_LOOKBACK_DAYS = 2
PRICE_MIN, PRICE_MAX = 2.0, 20.0
REL_VOL_THRESHOLD = 5.0

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
        actives = yf.screen("most_actives", count=20)
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
        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=NEWS_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
            news = client.company_news(symbol, _from=start, to=end)
            if news:
                has_news = True
                headline = news[0].get("headline", "")[:90]
        except Exception:
            pass

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
            "News": "Yes" if has_news else "No",
            "Headline": headline,
            "Score": score,
        }
    except Exception:
        return None

def run_scan():
    client = finnhub.Client(api_key=FINNHUB_API_KEY)
    seeds = get_seed_tickers()
    if not seeds:
        return pd.DataFrame()

    results = []
    progress = st.progress(0)
    status = st.empty()

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fetch_one, sym, client): sym for sym in seeds}
        done = 0
        total = len(seeds)
        for future in as_completed(futures):
            data = future.result()
            if data:
                results.append(data)
            done += 1
            progress.progress(done / total)
            status.text(f"Scanned {done} of {total}...")

    progress.empty()
    status.empty()

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df = df.sort_values(by=["Score", "% Change"], ascending=[False, False]).reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))
    return df

def color_score(val):
    if val >= 4:
        return "background-color: #166534; color: #bbf7d0"
    if val == 3:
        return "background-color: #854d0e; color: #fef08a"
    if val == 2:
        return "background-color: #9a3412; color: #fed7aa"
    return ""

def color_rvol(val):
    try:
        if val is not None and float(val) >= 5:
            return "background-color: #0e7490; color: #a5f3fc"
        if val is not None and float(val) >= 3:
            return "background-color: #1e3a5f; color: #7dd3fc"
    except Exception:
        pass
    return ""

def color_change(val):
    try:
        if float(val) >= 10:
            return "background-color: #166534; color: #bbf7d0"
        if float(val) > 0:
            return "color: #4ade80"
        if float(val) < 0:
            return "color: #f87171"
    except Exception:
        pass
    return ""

# Sidebar
with st.sidebar:
    st.markdown("### Settings")
    min_score = st.slider("Minimum Score", 0, 5, 2)
    st.markdown("---")
    st.markdown("""
    **Criteria (equal weight)**  
    1. Up ≥ 10% today  
    2. Rel Vol ≥ 5×  
    3. Recent News  
    4. Price $2 – $20  
    5. Float < 20M
    """)
    st.caption("Educational tool only. Not financial advice.")

# Header
st.markdown("## US Momentum Scanner")
st.caption("Dark terminal style · Conditional formatting · 5 criteria")
