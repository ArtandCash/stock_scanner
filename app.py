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

# Dark theme
st.markdown("""
<style>
    .stApp {
        background-color: #0b1220;
        color: #e0e6ed;
    }
    section[data-testid="stSidebar"] {
        background-color: #0f172a;
        border-right: 1px solid #1e293b;
    }
    h1, h2, h3, h4 {
        color: #f1f5f9 !important;
    }
    div[data-testid="stMetric"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 12px;
    }
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
st.caption("Dark terminal style · 5 equal-weight criteria")

# Scan button
if st.button("Scan Market Now", type="primary", use_container_width=True):
    with st.spinner("Scanning... this takes 30-60 seconds"):
        df = run_scan()
        st.session_state["df"] = df

df = st.session_state.get("df", None)

if df is None or df.empty:
    st.info("Click the Scan Market Now button above to start.")
else:
    display_df = df[df["Score"] >= min_score].copy()

    c1, c2, c3 = st.columns(3)
    c1.metric("Matches", len(display_df))
    c2.metric("High Conviction (Score ≥ 4)", len(df[df["Score"] >= 4]))
    c3.metric("Best Score", int(df["Score"].max()))

    st.markdown("### Momentum Rankings")
    st.dataframe(
        display_df[["Rank", "Symbol", "Price", "% Change", "Rel Vol", "Float (M)", "News", "Score"]],
        use_container_width=True,
        height=450,
        hide_index=True
    )

    st.markdown("### News Headlines")
    news_df = display_df[display_df["News"] == "Yes"][["Symbol", "Headline", "Score"]]
    if news_df.empty:
        st.write("No recent news among current matches.")
    else:
        st.dataframe(news_df, use_container_width=True, hide_index=True)

    csv = display_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, "scanner_results.csv", "text/csv")
