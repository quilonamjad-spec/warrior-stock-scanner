import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="Stock Price Tracker", layout="wide")

st.title("📈 Live Stock Price Tracker")

# ---------- Session State ----------
if "stocks" not in st.session_state:
    st.session_state.stocks = []

if "price_table" not in st.session_state:
    st.session_state.price_table = pd.DataFrame()

# ---------- Input ----------
stock_text = st.text_area(
    "Enter Stock Symbols (one per line)",
    height=180,
    placeholder="""RELIANCE
TCS
INFY
ICICIBANK
HDFCBANK"""
)

col1, col2, col3 = st.columns(3)

# ---------- Start Tracking ----------
if col1.button("▶ Start Tracking"):

    stocks = []

    for s in stock_text.splitlines():
        s = s.strip().upper()
        if s:
            if not s.endswith(".NS"):
                s += ".NS"
            stocks.append(s)

    stocks = stocks[:20]

    st.session_state.stocks = stocks
    st.session_state.price_table = pd.DataFrame(index=stocks)

# ---------- Refresh Prices ----------
if col2.button("🔄 Refresh Prices"):

    if len(st.session_state.stocks) == 0:
        st.warning("Start tracking first.")
    else:

        now = datetime.now().strftime("%H:%M")

        prices = []

        for stock in st.session_state.stocks:

            try:
                ticker = yf.Ticker(stock)
                price = ticker.fast_info["lastPrice"]
                prices.append(round(price, 2))

            except:
                prices.append(None)

        st.session_state.price_table[now] = prices

        st.success(f"Prices captured at {now}")

# ---------- Clear ----------
if col3.button("🗑 Clear"):

    st.session_state.stocks = []
    st.session_state.price_table = pd.DataFrame()

# ---------- Display ----------
if not st.session_state.price_table.empty:

    st.subheader("Price Tracker")

    st.dataframe(
        st.session_state.price_table,
        use_container_width=True
    )

    csv = st.session_state.price_table.to_csv().encode("utf-8")

    st.download_button(
        "📥 Export CSV",
        csv,
        file_name="prices.csv",
        mime="text/csv"
    )
