import streamlit as st
import yfinance as yf
import finnhub
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    page_title="Momentum Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===================== DESIGN =====================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    .stApp, .stApp * {
        font-family: 'Phonic', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    }
    .stApp {
        background-color: #070b14 !important;
        color: #e8edf5 !important;
    }
    .stApp p, .stApp span, .stApp label, .stApp div, .stApp li {
        color: #e8edf5 !important;
    }
    section[data-testid="stSidebar"] {
        background-color: #0c1220 !important;
        border-right: 1px solid #1a2332 !important;
    }
    section[data-testid="stSidebar"] * {
        color: #e8edf5 !important;
    }
    h1, h2, h3, h4 {
        color: #f0f4fa !important;
        font-weight: 600 !important;
    }
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #121a2b, #0e1522) !important;
        border: 1px solid #1e2a3d !important;
        border-radius: 10px !important;
        padding: 14px 16px !important;
    }
    .stButton > button {
        background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    .detail-card {
        background: linear-gradient(145deg, #121a2b, #0e1522);
        border: 1px solid #1e2a3d;
        border-radius: 12px;
        padding: 16px 18px;
        margin-bottom: 12px;
    }
    .criteria-box {
        background: #0f172a;
        border: 1px solid #1e2a3d;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 16px;
        font-size: 0.92rem;
    }
    .news-item {
        padding: 7px 0;
        border-bottom: 1px solid #1e2a3d;
        font-size: 0.9rem;
    }
    .news-item a {
        color: #7dd3fc !important;
        text-decoration: none;
    }
    .news-source {
        color: #64748b !important;
        font-size: 0.75rem;
    }
</style>
""", unsafe_allow_html=True)

FINNHUB_API_KEY = st.secrets.get("FINNHUB_API_KEY", "d9s6fc1r01qoo7o6rmngd9s6fc1r01qoo7o6rmo0")

# ===================== SEED LISTS =====================
UK_EU_SEEDS = [
    "BP.L", "SHEL.L", "HSBA.L", "VOD.L", "GSK.L", "AZN.L", "ULVR.L", "DGE.L",
    "RIO.L", "BHP.L", "GLEN.L", "AAL.L", "NG.L", "LLOY.L", "BARC.L", "NWG.L",
    "TSCO.L", "SBRY.L", "BT-A.L", "CNA.L", "SSE.L", "RR.L", "BA.L", "EXPN.L",
    "AUTO.L", "JD.L", "IHG.L", "WPP.L", "INF.L", "REL.L", "PRU.L", "AV.L",
    "SMT.L", "III.L", "LSEG.L", "CRH.L", "AHT.L", "SN.L", "DCC.L", "BNZL.L",
    "FRES.L", "POLY.L", "HOC.L", "AMER.L", "BOO.L", "CURY.L", "ASC.L",
    "SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "BAS.DE", "BMW.DE", "VOW3.DE",
    "MC.PA", "OR.PA", "AIR.PA", "SAN.PA", "TTE.PA", "BNP.PA", "AI.PA",
    "ASML.AS", "INGA.AS", "PHIA.AS", "UNA.AS", "AD.AS",
    "NESN.SW", "ROG.SW", "NOVN.SW", "UBSG.SW",
    "ENI.MI", "ISP.MI", "UCG.MI", "STM.MI"
]

CRYPTO_SEEDS = [
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD",
    "AVAX-USD", "DOT-USD", "LINK-USD", "MATIC-USD", "SHIB-USD", "LTC-USD", "BCH-USD",
    "ATOM-USD", "UNI-USD", "XLM-USD", "ETC-USD", "FIL-USD", "ICP-USD", "NEAR-USD",
    "APT-USD", "ARB-USD", "OP-USD", "INJ-USD", "SUI-USD", "SEI-USD", "TIA-USD",
    "PEPE-USD", "WIF-USD", "BONK-USD", "FLOKI-USD", "RENDER-USD", "FET-USD", "TAO-USD"
]

# ===================== DATA FUNCTIONS =====================
def get_us_seeds():
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
    return list(tickers)[:30]

def fetch_stock(symbol, client, market="US"):
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
            start = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
            base = symbol.split(".")[0]
            news = client.company_news(base, _from=start, to=end)
            if news:
                for n in news[:6]:
                    h = n.get("headline", "").strip()
                    u = n.get("url", "")
                    if h and u:
                        news_items.append({"headline": h[:100], "url": u, "source": n.get("source", "")})
        except Exception:
            pass

        if market == "US":
            c1 = pct_change >= 10
            c2 = rel_vol is not None and rel_vol >= 5
            c3 = len(news_items) > 0
            c4 = 2.0 <= price <= 20.0
            c5 = float_m is not None and float_m < 20
        else:
            c1 = pct_change >= 8
            c2 = rel_vol is not None and rel_vol >= 4
            c3 = len(news_items) > 0
            c4 = 0.05 <= price <= 15.0
            c5 = float_m is not None and float_m < 60

        score = sum([c1, c2, c3, c4, c5])
        return {
            "Symbol": symbol,
            "Price": round(price, 2),
            "% Change": round(pct_change, 2),
            "Rel Vol": round(rel_vol, 2) if rel_vol else None,
            "Float (M)": round(float_m, 2) if float_m else None,
            "News": "Yes" if news_items else "No",
            "Headline": news_items[0]["headline"] if news_items else "",
            "News Items": news_items,
            "Score": score
        }
    except Exception:
        return None

def fetch_crypto(symbol, client):
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        pct_change = info.get("regularMarketChangePercent")
        if price is None or pct_change is None:
            return None

        current_vol = info.get("volume24Hr") or info.get("regularMarketVolume") or 0
        avg_vol = info.get("averageVolume") or info.get("averageDailyVolume10Day")
        if not avg_vol:
            hist = t.history(period="1mo")
            avg_vol = hist["Volume"].tail(14).mean() if not hist.empty else None
        rel_vol = (current_vol / avg_vol) if avg_vol and avg_vol > 0 else None

        circ = info.get("circulatingSupply")
        circ_m = circ / 1_000_000 if circ else None

        news_items = []
        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
            base = symbol.replace("-USD", "")
            news = client.company_news(base, _from=start, to=end)
            if news:
                for n in news[:5]:
                    h = n.get("headline", "").strip()
                    u = n.get("url", "")
                    if h and u:
                        news_items.append({"headline": h[:100], "url": u, "source": n.get("source", "")})
        except Exception:
            pass

        c1 = pct_change >= 8
        c2 = rel_vol is not None and rel_vol >= 3
        c3 = len(news_items) > 0
        c4 = 0.05 <= price <= 50.0
        c5 = True
        score = sum([c1, c2, c3, c4, c5])

        return {
            "Symbol": symbol,
            "Price": round(price, 2),
            "% Change": round(pct_change, 2),
            "Rel Vol": round(rel_vol, 2) if rel_vol else None,
            "Circ Supply (M)": round(circ_m, 2) if circ_m else None,
            "News": "Yes" if news_items else "No",
            "Headline": news_items[0]["headline"] if news_items else "",
            "News Items": news_items,
            "Score": score
        }
    except Exception:
        return None

def run_scan(market):
    client = finnhub.Client(api_key=FINNHUB_API_KEY)
    if market == "US":
        seeds = get_us_seeds()
        fetch_fn = lambda s: fetch_stock(s, client, "US")
    elif market == "UK_EU":
        seeds = UK_EU_SEEDS
        fetch_fn = lambda s: fetch_stock(s, client, "UK_EU")
    else:
        seeds = CRYPTO_SEEDS
        fetch_fn = lambda s: fetch_crypto(s, client)

    results = []
    progress = st.progress(0)
    status = st.empty()
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fetch_fn, sym): sym for sym in seeds}
        done = 0
        total = len(seeds)
        for future in as_completed(futures):
            data = future.result()
            if data:
                results.append(data)
            done += 1
            progress.progress(done / total)
            status.text(f"Scanned {done}/{total}")
    progress.empty()
    status.empty()

    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    df = df.sort_values(by=["Score", "% Change"], ascending=[False, False]).reset_index(drop=True)
    df.insert(0, "Rank", range(1, len(df) + 1))
    return df

def make_chart(symbol, period, interval, title):
    try:
        hist = yf.Ticker(symbol).history(period=period, interval=interval)
        if hist.empty:
            return None
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                            row_heights=[0.72, 0.28],
                            subplot_titles=(f"{symbol} — {title}", "Volume"))
        fig.add_trace(go.Candlestick(
            x=hist.index, open=hist["Open"], high=hist["High"],
            low=hist["Low"], close=hist["Close"],
            increasing_line_color="#22c55e", decreasing_line_color="#ef4444"
        ), row=1, col=1)
        colors = ["#22c55e" if c >= o else "#ef4444" for o, c in zip(hist["Open"], hist["Close"])]
        fig.add_trace(go.Bar(x=hist.index, y=hist["Volume"], marker_color=colors, opacity=0.7), row=2, col=1)
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="#070b14", plot_bgcolor="#0c1220",
            font=dict(color="#e8edf5", size=11), height=380,
            margin=dict(l=8, r=8, t=36, b=8), xaxis_rangeslider_visible=False, showlegend=False
        )
        fig.update_xaxes(gridcolor="#1a2332")
        fig.update_yaxes(gridcolor="#1a2332")
        return fig
    except Exception:
        return None

def color_score(val):
    if val >= 4: return "background-color: #14532d; color: #bbf7d0"
    if val == 3: return "background-color: #713f12; color: #fef08a"
    if val == 2: return "background-color: #7c2d12; color: #fed7aa"
    return ""

def color_rvol(val):
    try:
        if val and float(val) >= 5: return "background-color: #0e7490; color: #a5f3fc"
        if val and float(val) >= 3: return "background-color: #1e3a5f; color: #7dd3fc"
    except: pass
    return ""

def color_change(val):
    try:
        if float(val) >= 10: return "background-color: #14532d; color: #bbf7d0"
        if float(val) > 0: return "color: #4ade80"
        if float(val) < 0: return "color: #f87171"
    except: pass
    return ""

def render_momentum_scanner(market, criteria_html):
    st.markdown(f'<div class="criteria-box">{criteria_html}</div>', unsafe_allow_html=True)

    key = f"df_{market}"
    if key not in st.session_state:
        with st.spinner(f"Loading {market} data…"):
            st.session_state[key] = run_scan(market)

    if st.button("Re-scan Now", type="primary", key=f"btn_{market}", use_container_width=True):
        with st.spinner("Scanning…"):
            st.session_state[key] = run_scan(market)

    df = st.session_state.get(key, None)
    if df is None or df.empty:
        st.info("No data yet. Click Re-scan Now.")
        return

    min_score = st.session_state.get("min_score", 2)
    display = df[df["Score"] >= min_score].copy()

    m1, m2, m3 = st.columns(3)
    m1.metric("Matches", len(display))
    m2.metric("High Conviction (≥4)", len(df[df["Score"] >= 4]))
    m3.metric("Best Score", int(df["Score"].max()) if not df.empty else 0)

    st.markdown("---")

    left, right = st.columns([1.55, 1])

    with left:
        st.markdown("#### Rankings")
        show_cols = [c for c in ["Rank", "Symbol", "Price", "% Change", "Rel Vol", "Float (M)", "Circ Supply (M)", "News", "Score"] if c in display.columns]
        table = display[show_cols].copy()

        format_dict = {
            "Price": "{:.2f}",
            "% Change": "{:+.2f}%",
            "Rel Vol": "{:.2f}x",
            "Float (M)": "{:.2f}",
            "Circ Supply (M)": "{:.2f}",
            "Score": "{:.0f}"
        }
        format_dict = {k: v for k, v in format_dict.items() if k in table.columns}

        styled = (table.style
                  .map(color_score, subset=["Score"])
                  .map(color_rvol, subset=["Rel Vol"])
                  .map(color_change, subset=["% Change"])
                  .format(format_dict, na_rep="—"))

        st.dataframe(styled, use_container_width=True, height=420, hide_index=True)

    selected = None
    with right:
        st.markdown("#### Detail & News")
        if len(display) > 0:
            selected = st.selectbox("Select stock", display["Symbol"].tolist(), key=f"sel_{market}")
            row = display[display["Symbol"] == selected].iloc[0]

            price_str = f"{row['Price']:.2f}"
            change_str = f"{row['% Change']:+.2f}%"
            rel_vol_str = f"{row['Rel Vol']:.2f}" if pd.notna(row.get("Rel Vol")) else "—"

            st.markdown(f"""
            <div class="detail-card">
                <strong style="font-size:1.2rem; color:#38bdf8;">{selected}</strong><br>
                <span style="font-size:1.4rem; font-weight:700;">
                    {price_str}
                    <span style="color:{'#4ade80' if row['% Change'] >= 0 else '#f87171'}; font-size:1rem;">
                        {change_str}
                    </span>
                </span><br>
                <span style="color:#94a3b8; font-size:0.9rem;">
                    Rel Vol: <b>{rel_vol_str}</b> · Score: <b style="color:#fbbf24">{row['Score']}</b>
                </span>
            </div>
            """, unsafe_allow_html=True)

            news_items = row.get("News Items") or []
            if news_items:
                st.markdown("**Top News**")
                for item in news_items[:5]:
                    st.markdown(
                        f'<div class="news-item"><a href="{item["url"]}" target="_blank">{item["headline"]}</a>'
                        f'<div class="news-source">{item.get("source", "")}</div></div>',
                        unsafe_allow_html=True
                    )
            else:
                st.caption("No recent news")
        else:
            st.info("No stocks match the filters.")

    if selected:
        st.markdown("---")
        st.markdown("#### Charts")
        c1, c2 = st.columns(2)
        with c1:
            fig = make_chart(selected, "3mo", "1d", "Daily")
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("Daily chart unavailable")
        with c2:
            fig = make_chart(selected, "10d", "1h", "Hourly")
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("Hourly chart unavailable")

    st.markdown("---")
    csv = display.drop(columns=["News Items"], errors="ignore").to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, f"scanner_{market}.csv", "text/csv", key=f"dl_{market}")

# ===================== SIDEBAR =====================
with st.sidebar:
    st.markdown("### Navigation")
    section = st.radio(
        "Select section",
        [
            "Stocks: Momentum Scanner",
            "Stocks: ATH / ATL",
            "Crypto: Momentum Scanner",
            "Crypto: ATH / ATL"
        ],
        label_visibility="collapsed"
    )

    st.markdown("---")
    st.markdown("### Settings")
    st.session_state.min_score = st.slider("Minimum Score", 0, 5, 2)
    
    auto_refresh = st.toggle("Auto-refresh every 90s", value=False)
    
    st.markdown("---")
    st.caption("Educational tool only. Not financial advice.")

# Auto-refresh
if auto_refresh:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=90_000, key="auto_refresh_90s")
    except ImportError:
        st.sidebar.warning("Add streamlit-autorefresh to requirements.txt")

# ===================== MAIN CONTENT =====================
st.markdown("## Momentum Scanner")

if section == "Stocks: Momentum Scanner":
    st.caption("US + UK/EU momentum scanners")
    
    tab1, tab2 = st.tabs(["🇺🇸 US Stocks", "🇬🇧 EU / UK Stocks"])
    
    with tab1:
        render_momentum_scanner("US", """
            <b>US Criteria (equal weight)</b><br>
            1. Up ≥ 10% today<br>
            2. Rel Vol ≥ 5×<br>
            3. Recent News<br>
            4. Price $2 – $20<br>
            5. Float < 20M
        """)
    
    with tab2:
        render_momentum_scanner("UK_EU", """
            <b>UK / EU Criteria (equal weight)</b><br>
            1. Up ≥ 8% today<br>
            2. Rel Vol ≥ 4×<br>
            3. Recent News<br>
            4. Price £0.05 – £15<br>
            5. Float < 60M
        """)

elif section == "Crypto: Momentum Scanner":
    st.caption("Crypto momentum scanner")
    render_momentum_scanner("Crypto", """
        <b>Crypto Criteria (equal weight)</b><br>
        1. Up ≥ 8% today<br>
        2. Rel Vol ≥ 3×<br>
        3. Recent News<br>
        4. Price $0.05 – $50<br>
        5. Circulating supply shown for reference
    """)

elif section == "Stocks: ATH / ATL":
    st.markdown("### Stocks: ATH / ATL Scanner")
    st.info("This section is ready. Please provide the criteria for the Stocks ATH / ATL scanner and I will build it.")

elif section == "Crypto: ATH / ATL":
    st.markdown("### Crypto: ATH / ATL Scanner")
    st.info("This section is ready. Please provide the criteria for the Crypto ATH / ATL scanner and I will build it.")
