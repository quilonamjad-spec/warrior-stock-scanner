import streamlit as st
import pandas as pd
import yfinance as yf
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

st.set_page_config(page_title="Live Stock Price Tracker", layout="wide")

st.title("📈 Live Stock Price Tracker")

st.markdown("Enter stock names (one per line). Example:")
st.code("""RELIANCE
TCS
INFY
ICICIBANK
HDFCBANK""")

stock_text = st.text_area(
    "Stocks",
    height=200,
    placeholder="Enter one stock per line..."
)

col1, col2 = st.columns(2)

start = col1.button("▶ Start Tracking")
clear = col2.button("🗑 Clear")

if clear:
    st.session_state.clear()
    st.rerun()

# Refresh every 5 minutes
st_autorefresh(interval=300000, key="refresh")

if start:

    stocks = [
        s.strip().upper() + ".NS"
        for s in stock_text.splitlines()
        if s.strip()
    ]

    stocks = stocks[:20]

    st.session_state["stocks"] = stocks

if "stocks" in st.session_state:

    stocks = st.session_state["stocks"]

    if "price_table" not in st.session_state:

        df = pd.DataFrame(index=stocks)

        st.session_state["price_table"] = df

    df = st.session_state["price_table"]

    now = datetime.now().strftime("%H:%M")

    if now not in df.columns:

        prices = []

        with st.spinner("Fetching prices..."):

            for stock in stocks:

                try:
                    ticker = yf.Ticker(stock)

                    price = ticker.fast_info["lastPrice"]

                    prices.append(round(price, 2))

                except:

                    prices.append(None)

        df[now] = prices

        st.session_state["price_table"] = df

        df.to_csv("prices.csv")

    st.subheader("Live Prices")

    st.dataframe(
        st.session_state["price_table"],
        use_container_width=True
    )

    csv = st.session_state["price_table"].to_csv().encode("utf-8")

    st.download_button(
        "📥 Export CSV",
        csv,
        file_name="prices.csv",
        mime="text/csv"
    )

    st.caption(f"Last Updated : {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")

else:

    st.info("Enter stocks and click **Start Tracking**.")
