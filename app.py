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

# ===================== SHARPER DARK DESIGN =====================
st.markdown("""
<style>
    /* Global */
    .stApp {
        background-color: #070b14 !important;
        color: #e8edf5 !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .stApp p, .stApp span, .stApp label, .stApp div, .stApp li {
        color: #e8edf5 !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #0c1220 !important;
        border-right: 1px solid #1a2332 !important;
    }
    section[data-testid="stSidebar"] * {
        color: #e8edf5 !important;
    }

    /* Headers */
    h1, h2, h3, h4 {
        color: #f0f4fa !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em;
    }

    /* Metric cards */
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #121a2b, #0e1522) !important;
        border: 1px solid #1e2a3d !important;
        border-radius: 10px !important;
        padding: 14px 16px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.25);
    }
    div[data-testid="stMetric"] label {
        color: #8b9bb4 !important;
        font-size: 0.8rem !important;
    }
    div[data-testid="stMetric"] div {
        color: #f0f4fa !important;
        font-weight: 600 !important;
    }

    /* Primary button */
    .stButton > button {
        background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.6rem 1.2rem !important;
        box-shadow: 0 2px 6px rgba(37,99,235,0.35);
        transition: all 0.15s ease;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #3b82f6, #2563eb) !important;
        box-shadow: 0 4px 12px rgba(37,99,235,0.45);
    }

    /* Dataframe */
    .stDataFrame {
        border: 1px solid #1e2a3d !important;
        border-radius: 10px !important;
        overflow: hidden;
    }

    /* Selectbox */
    .stSelectbox label {
        color: #8b9bb4 !important;
        font-size: 0.85rem !important;
    }

    /* Divider */
    hr {
        border-color: #1e2a3d !important;
        margin: 1.2rem 0 !important;
    }

    /* Custom card */
    .detail-card {
        background: linear-gradient(145deg, #121a2b, #0e1522);
        border: 1px solid #1e2a3d;
        border-radius: 12px;
        padding: 18px 20px;
        margin-bottom: 14px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.2);
    }
    .detail-card h3 {
        margin: 0 0 6px 0;
        color: #38bdf8 !important;
        font-size: 1.35rem;
    }
    .price-line {
        font-size: 1.7rem;
        font-weight: 700;
        margin: 4px 0 10px 0;
        color: #f0f4fa;
    }
    .meta-line {
        color: #8b9bb4 !important;
        font-size: 0.9rem;
        margin: 3px 0;
    }
    .news-item {
        padding: 8px 0;
        border-bottom: 1px solid #1e2a3d;
        font-size: 0.92rem;
    }
    .news-item a {
        color: #7dd3fc !important;
        text-decoration: none;
    }
    .news-item a:hover {
        color: #bae6fd !important;
        text-decoration: underline;
    }
    .news-source {
        color: #64748b !important;
        font-size: 0.78rem;
    }
</style>
""", unsafe_allow_html=True)

# ===================== CONFIG =====================
FINNHUB_API_KEY = st.secrets.get("FINNHUB_API_KEY", "d9s6fc1r01qoo7o6rmngd9s6fc1r01qoo7o6rmo0")
MAX_CANDIDATES = 25
NEWS_LOOKBACK_DAYS = 3
PRICE_MIN = 2.0
PRICE_MAX = 20.0
REL_VOL_THRESHOLD = 5.0

# ===================== HELPERS =====================
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

        news_items = []
        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=NEWS_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
            news = client.company_news(symbol, _from=start, to=end)
            if news:
                for n in news[:8]:
                    headline = n.get("headline", "").strip()
                    url = n.get("url", "")
                    source = n.get("source", "")
                    if headline and url:
                        news_items.append({
                            "headline": headline[:110],
                            "url": url,
                            "source": source
                        })
        except Exception:
            pass

        has_news = len(news_items) > 0
        headline = news_items[0]["headline"] if news_items else ""

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
            "News Items": news_items,
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

def make_candle_chart(symbol, period, interval, title):
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period=period, interval=interval)
        if hist.empty:
            return None

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.72, 0.28],
            subplot_titles=(f"{symbol} — {title}", "Volume")
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
            paper_bgcolor="#070b14",
            plot_bgcolor="#0c1220",
            font=dict(color="#e8edf5", size=11),
            height=390,
            margin=dict(l=8, r=8, t=36, b=8),
            xaxis_rangeslider_visible=False,
            showlegend=False
        )
        fig.update_xaxes(gridcolor="#1a2332")
        fig.update_yaxes(gridcolor="#1a2332")
        return fig
    except Exception:
        return None

def color_score(val):
    if val >= 4:
        return "background-color: #14532d; color: #bbf7d0"
    if val == 3:
        return "background-color: #713f12; color: #fef08a"
    if val == 2:
        return "background-color: #7c2d12; color: #fed7aa"
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
            return "background-color: #14532d; color: #bbf7d0"
        if float(val) > 0:
            return "color: #4ade80"
        if float(val) < 0:
            return "color: #f87171"
    except Exception:
        pass
    return ""

# ===================== SIDEBAR =====================
with st.sidebar:
    st.markdown("### Settings")
    min_score = st.slider("Minimum Score", 0, 5, 2)
    auto_refresh = st.toggle("Auto-refresh every 90s", value=False)
    st.markdown("---")
    st.markdown("**Criteria (equal weight)**")
    st.markdown("1. Up ≥ 10% today")
    st.markdown("2. Rel Vol ≥ 5×")
    st.markdown("3. Recent News")
    st.markdown("4. Price $2 – $20")
    st.markdown("5. Float < 20M")
    st.caption("Educational tool only. Not financial advice.")

# Auto-refresh
if auto_refresh:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=90_000, key="auto_refresh")
    except ImportError:
        st.sidebar.warning("Install streamlit-autorefresh for auto-refresh")

# ===================== HEADER =====================
st.markdown("## US Momentum Scanner")
st.caption("Professional dark terminal · Conditional formatting · Live news links")

# Scan button
scan_clicked = st.button("Scan Market Now", type="primary", use_container_width=True)

if scan_clicked:
    with st.spinner("Scanning market… 30–60 seconds"):
        df = run_scan()
        st.session_state["df"] = df

df = st.session_state.get("df", None)

if df is None or df.empty:
    st.info("Click **Scan Market Now** to load live results.")
else:
    display_df = df[df["Score"] >= min_score].copy()

    m1, m2, m3 = st.columns(3)
    m1.metric("Matches", len(display_df))
    m2.metric("High Conviction (≥4)", len(df[df["Score"] >= 4]))
    m3.metric("Best Score", int(df["Score"].max()))

    st.markdown("---")

    left, right = st.columns([1.55, 1])

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
        }, na_rep="—")

        st.dataframe(styled, use_container_width=True, height=430, hide_index=True)

    with right:
        st.markdown("### Stock Detail")
        if len(display_df) > 0:
            symbols = display_df["Symbol"].tolist()
            selected = st.selectbox("Select stock", symbols, label_visibility="collapsed")
            row = display_df[display_df["Symbol"] == selected].iloc[0]

            # Detail card
            change_color = "#4ade80" if row["% Change"] >= 0 else "#f87171"
            st.markdown(f"""
            <div class="detail-card">
                <h3>{selected}</h3>
                <div class="price-line">
                    ${row['Price']:.2f}
                    <span style="color:{change_color}; font-size:1.15rem; margin-left:8px;">
                        {row['% Change']:+.1f}%
                    </span>
                </div>
                <div class="meta-line">Rel Vol: <b style="color:#67e8f9">{row['Rel Vol'] if row['Rel Vol'] else '—'}x</b>
                    &nbsp;·&nbsp; Float: <b>{row['Float (M)'] if row['Float (M)'] else '—'}M</b>
                    &nbsp;·&nbsp; Score: <b style="color:#fbbf24">{row['Score']}</b>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Top 5 News with hyperlinks
            st.markdown("#### Top News")
            news_items = row.get("News Items") or []
            if news_items:
                for item in news_items[:5]:
                    source = item.get("source", "")
                    st.markdown(
                        f'<div class="news-item">'
                        f'<a href="{item["url"]}" target="_blank">{item["headline"]}</a>'
                        f'<div class="news-source">{source}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
            else:
                st.caption("No recent news found.")
        else:
            st.info("No stocks match the current filters.")
            selected = None

    # Charts
    if len(display_df) > 0 and selected:
        st.markdown("---")
        st.markdown("### Charts")
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**Daily**")
            fig1 = make_candle_chart(selected, period="3mo", interval="1d", title="By Day")
            if fig1:
                st.plotly_chart(fig1, use_container_width=True)
            else:
                st.caption("Daily chart unavailable")

        with c2:
            st.markdown("**Hourly**")
            fig2 = make_candle_chart(selected, period="10d", interval="1h", title="By Hour")
            if fig2:
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.caption("Hourly chart unavailable")

    # High conviction
    st.markdown("---")
    st.markdown("### High Conviction (Score ≥ 3)")
    top = df[df["Score"] >= 3][
        ["Rank", "Symbol", "Price", "% Change", "Rel Vol", "Float (M)", "Score", "Headline"]
    ].head(10)
    if not top.empty:
        st.dataframe(top, use_container_width=True, hide_index=True)
    else:
        st.caption("No high-conviction names this scan.")

    csv = display_df.drop(columns=["News Items"], errors="ignore").to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, "scanner_results.csv", "text/csv")
