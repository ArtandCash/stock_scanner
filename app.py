import streamlit as st
import yfinance as yf
import finnhub
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    page_title="US Momentum Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp {
        background-color: #0b1220 !important;
        color: #f1f5f9 !important;
    }
    .stApp p, .stApp span, .stApp label, .stApp div {
        color: #f1f5f9 !important;
    }
    section[data-testid="stSidebar"] {
        background-color: #0f172a !important;
    }
    section[data-testid="stSidebar"] * {
        color: #f1f5f9 !important;
    }
    h1, h2, h3, h4 {
        color: #f1f5f9 !important;
    }
    div[data-testid="stMetric"] {
        background-color: #1e293b !important;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 12px;
    }
    .stButton > button {
        background-color: #3b82f6 !important;
        color: white !important;
        border-radius: 6px;
        border: none;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

FINNHUB_API_KEY = st.secrets.get("FINNHUB_API_KEY", "d9s6fc1r01qoo7o6rmngd9s6fc1r01qoo7o6rmo0")
MAX_CANDIDATES = 25
NEWS_LOOKBACK_DAYS = 2
PRICE_MIN = 2.0
PRICE_MAX = 20.0
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
            "Score": score
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
            status.text(f"Scanned {done} of {total}")

    progress.empty()
    status.empty()

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df = df.sort_values(by=["Score", "% Change"], ascending=[False, False])
    df = df.reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))
    return df

def make_candle_chart(symbol, period="5d", interval="15m", title="Intraday"):
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period=period, interval=interval)
        if hist.empty:
            hist = t.history(period="1mo", interval="1d")
            title = "Daily"
        if hist.empty:
            return None

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.72, 0.28],
            subplot_titles=(f"{symbol} - {title}", "Volume")
        )

        fig.add_trace(
            go.Candlestick(
                x=hist.index,
                open=hist["Open"],
                high=hist["High"],
                low=hist["Low"],
                close=hist["Close"],
                increasing_line_color="#22c55e",
                decreasing_line_color="#ef4444",
                name="Price"
            ),
            row=1, col=1
        )

        colors = ["#22c55e" if c >= o else "#ef4444" for o, c in zip(hist["Open"], hist["Close"])]
        fig.add_trace(
            go.Bar(
                x=hist.index,
                y=hist["Volume"],
                marker_color=colors,
                opacity=0.7,
                name="Volume"
            ),
            row=2, col=1
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0b1220",
            plot_bgcolor="#0f172a",
            font=dict(color="#e0e6ed"),
            height=380,
            margin=dict(l=10, r=10, t=40, b=10),
            xaxis_rangeslider_visible=False,
            showlegend=False
        )
        fig.update_xaxes(gridcolor="#1e293b")
        fig.update_yaxes(gridcolor="#1e293b")
        return fig
    except Exception:
        return None

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
    st.markdown("**Criteria (equal weight)**")
    st.markdown("1. Up ≥ 10% today")
    st.markdown("2. Rel Vol ≥ 5x")
    st.markdown("3. Recent News")
    st.markdown("4. Price $2 – $20")
    st.markdown("5. Float < 20M")
    st.caption("Educational tool only. Not financial advice.")

# Header
st.markdown("## US Momentum Scanner")
st.caption("Dark terminal style - Conditional formatting - 5 criteria")

# Scan button
scan_clicked = st.button("Scan Market Now", type="primary", use_container_width=True)

if scan_clicked:
    with st.spinner("Scanning... please wait 30-60 seconds"):
        df = run_scan()
        st.session_state["df"] = df

df = st.session_state.get("df", None)

if df is None or df.empty:
    st.info("Click the Scan Market Now button above to start.")
else:
    display_df = df[df["Score"] >= min_score].copy()

    m1, m2, m3 = st.columns(3)
    m1.metric("Matches", len(display_df))
    m2.metric("High Conviction (Score >= 4)", len(df[df["Score"] >= 4]))
    m3.metric("Best Score", int(df["Score"].max()))

    st.markdown("---")

    left, right = st.columns([1.5, 1])

    with left:
        st.markdown("### Momentum Rankings")
        cols = ["Rank", "Symbol", "Price", "% Change", "Rel Vol", "Float (M)", "News", "Score"]
        table = display_df[cols].copy()

        styled = table.style.map(color_score, subset=["Score"])
        styled = styled.map(color_rvol, subset=["Rel Vol"])
        styled = styled.map(color_change, subset=["% Change"])
        styled = styled.format({
            "Price": "${:.2f}",
            "% Change": "{:+.1f}%",
            "Rel Vol": "{:.1f}x",
            "Float (M)": "{:.1f}",
            "Score": "{:.0f}"
        }, na_rep="-")

        st.dataframe(styled, use_container_width=True, height=420, hide_index=True)

    with right:
        st.markdown("### Stock Detail")
        if len(display_df) > 0:
            symbols = display_df["Symbol"].tolist()
            selected = st.selectbox("Select stock", symbols)
            row = display_df[display_df["Symbol"] == selected].iloc[0]

            st.markdown(f"**{selected}**")
            st.markdown(f"### ${row['Price']:.2f} ({row['% Change']:+.1f}%)")
            st.write(f"Rel Vol: **{row['Rel Vol'] if row['Rel Vol'] else '-'}x**")
            st.write(f"Float: **{row['Float (M)'] if row['Float (M)'] else '-'}M**")
            st.write(f"Score: **{row['Score']}**")
            st.write(f"News: **{row['News']}**")

            if row["Headline"]:
                st.markdown("#### Latest Headline")
                st.write(row["Headline"])
        else:
            st.info("No stocks match the current filters.")
            selected = None

    # ---------- TWO CHARTS SECTION ----------
    if len(display_df) > 0 and selected:
        st.markdown("---")
        st.markdown("### Charts")

        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            fig1 = make_candle_chart(selected, period="5d", interval="15m", title="Intraday (15m)")
            if fig1:
                st.plotly_chart(fig1, use_container_width=True)
            else:
                st.caption("Intraday chart unavailable")

        with chart_col2:
            fig2 = make_candle_chart(selected, period="1mo", interval="1d", title="Daily")
            if fig2:
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.caption("Daily chart unavailable")

    st.markdown("---")
    st.markdown("### High Conviction (Score >= 3)")
    top = df[df["Score"] >= 3][["Rank", "Symbol", "Price", "% Change", "Rel Vol", "Float (M)", "Score", "Headline"]].head(10)
    if not top.empty:
        st.dataframe(top, use_container_width=True, hide_index=True)
    else:
        st.caption("No high-conviction names this scan.")

    csv = display_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, "scanner_results.csv", "text/csv")
