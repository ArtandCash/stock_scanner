# US Momentum Stock Scanner

Live ranked scanner for US stocks based on 5 equal-weight criteria:

1. **Price already up ≥ 10%** on the day  
2. **Relative Volume ≥ 5×**  
3. **Recent news event** (last 2 days via Finnhub)  
4. **Price between $2 and $20**  
5. **Float < 20 million shares**

Stocks are ranked by **Score** (0–5) then by % change.

## Quick Start (local)

```bash
cd stock_scanner
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
