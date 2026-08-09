import streamlit as st
import yfinance as yf
import finnhub
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    page_title="US Momentum Scanner",
    page_icon="📈",
    layout="wide"
)

# ---------------- CONFIG ----------------
FINNHUB_API_KEY = st.secrets.get("FINNHUB_API_KEY", "d9s6fc1r01qoo7o6rmngd9s6fc1r01qoo7o6rmo0")
MAX_CANDIDATES = 25
NEWS_LOOKBACK_DAYS = 2
PRICE_MIN, PRICE_MAX = 2.0, 20.0
REL_VOL_THRESHOLD = 5.0
FLOAT_THRESHOLD = 20_000_000

st.title("📈 US Momentum Stock Scanner")
st.caption("5 equal-weight criteria · Ranked table · Yahoo Finance + Finnhub")

with st.sidebar:
    st.header("Settings")
    min_score = st.slider("Show only Score ≥", 0, 5, 2)
    st.markdown("---")
    st.markdown("""
    **Criteria (equal weight)**  
    1. Price up ≥ 10% today  
    2. Relative Volume ≥ 5×  
    3. Recent news (last 2 days)  
    4. Price between $2 – $20  
    5. Float < 20 million shares  
    """)
    st.markdown("---")
    st.markdown("Educational tool only. Not financial advice.")

# ---------------- HELPERS ----------------
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
    except Exception as e:
        st.warning(f"Could not load day gainers: {e}")

    try:
        actives = yf.screen("most_actives", count=20)
        for q in actives.get("quotes", []):
            sym = q.get("symbol")
            price = q.get("regularMarketPrice") or 0
            if sym and 1 <= price <= 40:
                tickers.add(sym)
    except Exception as e:
        st.warning(f"Could not load most actives: {e}")

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
                headline = news[0].get("headline", "")[:80]
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
            "C1 Up10%": c1,
            "C2 RVol5x": c2,
            "C3 News": c3,
            "C4 $2-20": c4,
            "C5 Float<20M": c5,
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
        for future in as_completed(futures):
            data = future.result()
            if data:
                results.append(data)
            done += 1
            progress.progress(done / len(seeds))
            status.text(f"Scanned {done} of {len(seeds)} stocks...")

    progress.empty()
    status.empty()

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df = df.sort_values(by=["Score", "% Change"], ascending=[False, False]).reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))
    return df


# ---------------- MAIN UI ----------------
if st.button("🔄 Scan Market Now", type="primary", use_container_width=True):
    with st.spinner("Scanning... this may take 30–60 seconds"):
        df = run_scan()

    if df.empty:
        st.warning("No candidates found right now. Try again during US market hours.")
    else:
        display_df = df[df["Score"] >= min_score].copy()

        st.success(f"Scan complete — {len(display_df)} stocks shown")

        col1, col2, col3 = st.columns(3)
        col1.metric("Best Score", int(df["Score"].max()))
        col2.metric("High conviction (Score ≥ 4)", len(df[df["Score"] >= 4]))
        col3.metric("Showing", len(display_df))

        st.dataframe(
            display_df[[
                "Rank", "Symbol", "Price", "% Change", "Rel Vol", "Float (M)",
                "News", "Score",
                "C1 Up10%", "C2 RVol5x", "C3 News", "C4 $2-20", "C5 Float<20M"
            ]],
            use_container_width=True,
            height=500,
            hide_index=True
        )

        with st.expander("News headlines"):
            news_df = display_df[display_df["News"] == "Yes"][["Symbol", "Headline", "Score"]]
            if news_df.empty:
                st.write("No recent news among current matches.")
            else:
                st.dataframe(news_df, use_container_width=True, hide_index=True)

        csv = display_df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download CSV", csv, "scanner_results.csv", "text/csv")

else:
    st.info("Click the **Scan Market Now** button above to start.")
