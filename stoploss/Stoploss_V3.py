import time
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="NSE Trailing SL Calculator", page_icon="📈", layout="centered"
)

REFRESH_SECONDS = 5
TRAILING_GAP = 0.0030  # Fixed 0.30% gap after 1% profit


def normalise_symbol(symbol):
    formatted_symbol = symbol.upper().strip()
    if not (formatted_symbol.endswith(".NS") or formatted_symbol.endswith(".BO")):
        formatted_symbol += ".NS"
    return formatted_symbol


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def fetch_nse_price_cached(formatted_symbol):
    """Cache Yahoo requests so repeated clicks within a few seconds reuse data."""
    ticker = yf.Ticker(formatted_symbol)
    df = ticker.history(period="1d", interval="1m")
    if df.empty:
        return None
    return float(df["Close"].iloc[-1])


def fetch_nse_price(symbol):
    formatted_symbol = normalise_symbol(symbol)
    try:
        live_price = fetch_nse_price_cached(formatted_symbol)
        return formatted_symbol, live_price
    except Exception:
        return formatted_symbol, None


def milestone_price(entry_price, profit_pct, is_buy):
    return entry_price * (1 + profit_pct) if is_buy else entry_price * (1 - profit_pct)


def milestone_sl(entry_price, profit_pct, is_buy):
    """SL that should be set exactly when a milestone is reached."""
    if profit_pct < 0.005:
        sl_pct = -0.005
    elif profit_pct < 0.0075:
        sl_pct = 0.0
    elif profit_pct < 0.010:
        sl_pct = profit_pct - 0.005
    else:
        sl_pct = 0.007
    return entry_price * (1 + sl_pct) if is_buy else entry_price * (1 - sl_pct)


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
        help="Milestone protection is active. After 1% profit, the SL uses a fixed 0.30% ratchet gap.",
    )

# Persistent state for the trade and Yahoo fallback.
def ensure_state():
    defaults = {
        "ratchet_key": None,
        "stop_loss": None,
        "highest_profit_pct": None,
        "highest_price": None,
        "last_successful_price": None,
        "last_successful_symbol": None,
        "last_fetch_time": 0.0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


ensure_state()

manual_price = st.number_input(
    "Manual Market Price (optional fallback)", min_value=0.0, value=0.0, step=0.05,
    help="Leave at 0 to use Yahoo Finance. If Yahoo is temporarily rate-limited, enter the current price here.",
)

calculate = st.button("🔄 Fetch Live Price & Calculate", use_container_width=True)

if calculate:
    formatted_symbol = normalise_symbol(symbol_input)
    using_cached_session_price = False
    source_note = None

    if manual_price > 0:
        live_price = manual_price
        source_note = "Using manually entered market price."
    else:
        now = time.time()
        same_symbol = st.session_state.last_successful_symbol == formatted_symbol
        elapsed = now - st.session_state.last_fetch_time

        # A session-level guard avoids hammering Yahoo even before the cache layer.
        if same_symbol and st.session_state.last_successful_price is not None and elapsed < REFRESH_SECONDS:
            live_price = st.session_state.last_successful_price
            using_cached_session_price = True
            remaining = max(0, REFRESH_SECONDS - elapsed)
            source_note = f"Using last fetched price to protect Yahoo Finance. Fresh fetch available in about {remaining:.1f}s."
        else:
            with st.spinner("Fetching live NSE price via yfinance..."):
                _, live_price = fetch_nse_price(formatted_symbol)

            if live_price is not None:
                st.session_state.last_successful_price = live_price
                st.session_state.last_successful_symbol = formatted_symbol
                st.session_state.last_fetch_time = now
                source_note = "Live price fetched successfully."
            elif same_symbol and st.session_state.last_successful_price is not None:
                live_price = st.session_state.last_successful_price
                using_cached_session_price = True
                source_note = "Yahoo Finance did not respond. Using the last successful price instead."

    if live_price is None:
        st.error(
            f"Could not fetch a price for '{symbol_input}'. Wait a few seconds and try again, or enter the market price manually."
        )
    else:
        if source_note:
            if using_cached_session_price:
                st.info(source_note)
            else:
                st.caption(source_note)

        is_buy = action == "BUY"
        profit_pct = (
            (live_price - entry_price) / entry_price
            if is_buy
            else (entry_price - live_price) / entry_price
        )

        initial_sl = entry_price * (1 - 0.005) if is_buy else entry_price * (1 + 0.005)
        target_tp = milestone_price(entry_price, 0.010, is_buy)

        trade_key = (formatted_symbol, action, round(entry_price, 4))
        if st.session_state.ratchet_key != trade_key:
            st.session_state.ratchet_key = trade_key
            st.session_state.stop_loss = initial_sl
            st.session_state.highest_profit_pct = profit_pct
            st.session_state.highest_price = live_price

        st.session_state.highest_profit_pct = max(
            st.session_state.highest_profit_pct, profit_pct
        )
        if is_buy:
            st.session_state.highest_price = max(st.session_state.highest_price, live_price)
        else:
            st.session_state.highest_price = min(st.session_state.highest_price, live_price)

        peak_profit = st.session_state.highest_profit_pct
        peak_price = st.session_state.highest_price

        if peak_profit >= 0.010:
            locked_sl = milestone_sl(entry_price, 0.010, is_buy)
            trailing_sl = peak_price * (1 - TRAILING_GAP) if is_buy else peak_price * (1 + TRAILING_GAP)
            candidate_sl = max(locked_sl, trailing_sl) if is_buy else min(locked_sl, trailing_sl)
            status_msg = (
                f"🎯 1.00% Profit Reached! SL locked at minimum +0.70%; "
                f"then ratcheting with a fixed {TRAILING_GAP * 100:.2f}% gap from the peak price"
            )
            badge_type = "success"
        elif peak_profit >= 0.0075:
            # 0.05% profit steps: 0.75 -> 0.25 SL, 0.80 -> 0.30 SL, etc.
            stepped_profit = (int((peak_profit * 100 + 1e-9) / 0.05) * 0.05) / 100
            sl_profit_pct = max(0.0025, stepped_profit - 0.0050)
            candidate_sl = entry_price * (1 + sl_profit_pct) if is_buy else entry_price * (1 - sl_profit_pct)
            status_msg = f"📈 Profit Ratchet Active — Peak {peak_profit * 100:.2f}%, SL locked at +{sl_profit_pct * 100:.2f}%"
            badge_type = "info"
        elif peak_profit >= 0.005:
            candidate_sl = entry_price
            status_msg = "⚡ 0.50% Milestone Reached — SL moved to Break-Even"
            badge_type = "warning"
        else:
            candidate_sl = initial_sl
            status_msg = "⏳ Price below trailing triggers (Original -0.50% SL)"
            badge_type = "secondary"

        # The ratchet: SL never moves backward.
        if is_buy:
            st.session_state.stop_loss = max(st.session_state.stop_loss, candidate_sl)
        else:
            st.session_state.stop_loss = min(st.session_state.stop_loss, candidate_sl)

        new_sl = st.session_state.stop_loss

        st.divider()
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

        # Anticipatory milestone guide.
        st.divider()
        st.subheader("🎯 Next Stop-Loss Milestones")
        st.caption("Use this as your advance guide: when market price reaches the milestone, move the SL to the shown level.")

        milestones = [0.005, 0.0075, 0.0080, 0.0085, 0.0090, 0.0095, 0.0100]
        rows = []
        for p in milestones:
            trigger_price = milestone_price(entry_price, p, is_buy)
            planned_sl = milestone_sl(entry_price, p, is_buy)
            reached = peak_profit >= p
            rows.append({
                "Status": "✓ Reached" if reached else "→ Upcoming",
                "Profit": f"{p * 100:.2f}%",
                "When price reaches": f"₹{trigger_price:.2f}",
                "Set Stop Loss to": f"₹{planned_sl:.2f}",
            })

        st.dataframe(rows, use_container_width=True, hide_index=True)

        if peak_profit < 0.010:
            next_levels = [p for p in milestones if p > peak_profit + 1e-12]
            if next_levels:
                next_p = next_levels[0]
                next_trigger = milestone_price(entry_price, next_p, is_buy)
                next_sl = milestone_sl(entry_price, next_p, is_buy)
                st.success(
                    f"NEXT MOVE: When price reaches ₹{next_trigger:.2f} ({next_p * 100:.2f}% profit), "
                    f"move your Stop Loss to ₹{next_sl:.2f}."
                )
        else:
            st.success(
                f"TARGET MODE: 1% has been reached. Continue using the 0.30% ratchet from the highest favorable price ₹{peak_price:.2f}."
            )
