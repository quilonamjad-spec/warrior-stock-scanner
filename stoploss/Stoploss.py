import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="NSE Trailing SL Calculator", page_icon="📈", layout="centered"
)


def fetch_nse_price(symbol):
    formatted_symbol = symbol.upper().strip()
    if not (
        formatted_symbol.endswith(".NS") or formatted_symbol.endswith(".BO")
    ):
        formatted_symbol += ".NS"

    ticker = yf.Ticker(formatted_symbol)
    df = ticker.history(period="1d", interval="1m")

    if df.empty:
        return None, None
    return formatted_symbol, float(df["Close"].iloc[-1])


st.title("📈 Trailing Stop Loss Calculator")
st.caption("NSE Market Protection Tool")

col1, col2 = st.columns(2)
with col1:
    symbol_input = st.text_input("Stock Symbol", value="SARDAEN")
    action = st.selectbox("Action", ["BUY", "SELL"])
with col2:
    entry_price = st.number_input(
        "Entry Price (₹)", min_value=0.0, value=500.0, step=0.05
    )
    is_whipsaw_safe = st.checkbox(
        "Whipsaw Safe Mode (0.40% Gap)",
        value=True,
        help="Expands trailing gap to 0.40% and adds buffers to handle spike wicks.",
    )

trailing_gap = 0.0040 if is_whipsaw_safe else 0.0025

if st.button("🔄 Fetch Live Price & Calculate", use_container_width=True):
    with st.spinner("Fetching live NSE price via yfinance..."):
        formatted_symbol, live_price = fetch_nse_price(symbol_input)

    if live_price is None:
        st.error(
            f"Could not fetch data for '{symbol_input}'. Check the symbol or enter market price manually."
        )
    else:
        is_buy = action == "BUY"
        profit_pct = (
            (live_price - entry_price) / entry_price
            if is_buy
            else (entry_price - live_price) / entry_price
        )

        initial_sl = (
            entry_price * (1 - 0.005) if is_buy else entry_price * (1 + 0.005)
        )
        target_tp = (
            entry_price * (1 + 0.010) if is_buy else entry_price * (1 - 0.010)
        )

        if profit_pct >= 0.010:
            new_sl = (
                live_price * (1 - trailing_gap)
                if is_buy
                else live_price * (1 + trailing_gap)
            )
            status_msg = f"🎯 Target (1.00%+) Reached! Maintaining {(trailing_gap*100):.2f}% Gap"
            badge_type = "success"
        elif profit_pct >= 0.0075:
            sl_buffer = 0.0015 if is_whipsaw_safe else 0.0025
            new_sl = (
                entry_price * (1 + sl_buffer)
                if is_buy
                else entry_price * (1 - sl_buffer)
            )
            status_msg = "📈 0.75% Profit Milestone Reached"
            badge_type = "info"
        elif profit_pct >= 0.005:
            sl_buffer = 0.0010 if is_whipsaw_safe else 0.0
            new_sl = (
                entry_price * (1 - sl_buffer)
                if is_buy
                else entry_price * (1 + sl_buffer)
            )
            status_msg = "⚡ 0.50% Profit Milestone (Break-Even/Buffered SL)"
            badge_type = "warning"
        else:
            new_sl = initial_sl
            status_msg = "⏳ Price below trailing triggers (Original -0.50% SL)"
            badge_type = "secondary"

        st.divider()

        # Display Metrics
        m1, m2, m3 = st.columns(3)
        m1.metric("Live Market Price", f"₹{live_price:.2f}")
        m2.metric("P&L %", f"{profit_pct * 100:+.2f}%")
        m3.metric("Target (1.0%)", f"₹{target_tp:.2f}")

        if badge_type == "success":
            st.success(status_msg)
        elif badge_type == "info":
            st.info(status_msg)
        else:
            st.warning(status_msg)

        st.metric(label="UPDATED STOP LOSS LEVEL", value=f"₹{new_sl:.2f}")