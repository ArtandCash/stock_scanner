def render_scanner(market, criteria_html):
    # Show criteria for this tab
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

        # Force 2 decimal places on numeric columns
        format_dict = {
            "Price": "{:.2f}",
            "% Change": "{:+.2f}%",
            "Rel Vol": "{:.2f}x",
            "Float (M)": "{:.2f}",
            "Circ Supply (M)": "{:.2f}",
            "Score": "{:.0f}"
        }
        # Only keep formats for columns that actually exist
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

    # Charts full width BELOW rankings
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
