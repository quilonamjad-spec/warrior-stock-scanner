import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="Intraday Price Tracker", layout="wide")

st.title("📈 Intraday Stock Price Tracker")
st.write("Shows today's 5-minute prices from market open (09:15 AM).")

# ------------------------------
# Input
# ------------------------------

stocks_text = st.text_area(
    "Enter Stock Symbols (one per line)",
    height=180,
    placeholder="""RELIANCE
TCS
INFY
ICICIBANK
HDFCBANK"""
)

col1, col2 = st.columns([1,1])

refresh = col1.button("🔄 Refresh Prices")
clear = col2.button("🗑 Clear")

if clear:
    st.rerun()

# ------------------------------
# Download Data
# ------------------------------

if refresh:

    stocks = []

    for s in stocks_text.splitlines():

        s = s.strip().upper()

        if s == "":
            continue

        if not s.endswith(".NS"):
            s += ".NS"

        stocks.append(s)

    stocks = stocks[:20]

    if len(stocks) == 0:
        st.warning("Please enter at least one stock.")
        st.stop()

    final_df = pd.DataFrame()

    progress = st.progress(0)

    for i, stock in enumerate(stocks):

        try:

            df = yf.download(
                stock,
                period="1d",
                interval="5m",
                progress=False,
                auto_adjust=True
            )

            if df.empty:
                continue

            # Keep only Close prices
            df = df[["Close"]]

            # Time as HH:MM
            df.index = df.index.strftime("%H:%M")

            # Transpose
            row = df.T

            row.index = [stock]
            final_df = final_df.round(2)

            final_df = pd.concat([final_df, row])

        except Exception as e:

            st.warning(f"Unable to fetch {stock}")

        progress.progress((i + 1) / len(stocks))

    progress.empty()

    if final_df.empty:
        st.error("No data available.")
        st.stop()

    st.success("Prices Updated")

    st.dataframe(final_df, use_container_width=True)

    csv = final_df.to_csv().encode("utf-8")

    st.download_button(
        "📥 Export CSV",
        csv,
        file_name=f"intraday_prices_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )
