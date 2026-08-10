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
