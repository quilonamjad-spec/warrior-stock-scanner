import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Warrior Candlestick Pattern Engine", layout="wide")
st.title("🛡️ Warrior Advanced Pattern Engine")
st.markdown("Automates strict multi-variable pattern tracking from your Warrior Trading Guide reference structures.")

# --- SIDEBAR INTERFACE CONTROLS ---
st.sidebar.header("🕹️ Execution Directives")
exchange = st.sidebar.selectbox("Exchange Registry:", ["NSE (.NS)", "BSE (.BO)"])
raw_ticker = st.sidebar.text_input("Asset Ticker Symbol:", "TCS")
trading_tf = st.sidebar.selectbox("Trading Timeframe (Execution):", ["5m", "15m", "30m"])
trend_tf = st.sidebar.selectbox("Trend Anchor Timeframe (Filter):", ["1h", "2h", "1d"])

st.sidebar.markdown("---")
st.sidebar.subheader("📅 Level Boundaries Strategy")
boundary_mode = st.sidebar.radio(
    "Select Structural Range Source:",
    ["Purely Today's Session", "Multi-Day Rolling Window (Last 30 Candles)"]
)

st.sidebar.markdown("---")
st.sidebar.subheader("🎛️ Sensitivity Thresholds")
vol_sigma = st.sidebar.slider("Required Volume Shock (Z-Score Sigma):", 1.0, 3.0, 1.5, step=0.1)
proximity_buffer_pct = st.sidebar.slider("Zone Proximity Buffer Sensitivity (%):", 0.1, 1.0, 0.3, step=0.05) / 100
max_ema_extension = st.sidebar.slider("Max Allowed Extension from 9 EMA (%):", 0.5, 3.0, 1.5, step=0.1) / 100

ticker = f"{raw_ticker.strip().upper()}.NS" if exchange == "NSE (.NS)" else f"{raw_ticker.strip().upper()}.BO"

# --- MULTI-TIMEFRAME DATA ENGINE ---
@st.cache_data(ttl=15)
def pull_clean_feed(symbol, interval, period="1mo"):
    try:
        data = yf.download(symbol, period=period, interval=interval, group_by='ticker')
        if data.empty: return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(-1)
        return data.loc[:, ~data.columns.duplicated()]
    except:
        return None

df_trade = pull_clean_feed(ticker, trading_tf)
df_trend = pull_clean_feed(ticker, trend_tf, period="3mo")

if df_trade is None or df_trade.empty or df_trend is None or df_trend.empty:
    st.error("❌ Analytical data connection broken. Verify ticker handle syntax.")
else:
    # --- HIGHER TIMEFRAME TREND FILTER ---
    df_trend['EMA_20'] = df_trend['Close'].ewm(span=20, adjust=False).mean()
    higher_tf_is_bullish = df_trend['Close'].iloc[-1] > df_trend['EMA_20'].iloc[-1]
    trend_status_text = "🟢 Bullish (Above 20 EMA)" if higher_tf_is_bullish else "🔴 Bearish (Below 20 EMA)"

    # --- MAIN TRADING TIMEFRAME CALCULATIONS ---
    trade_df = df_trade.copy()
    trade_df['EMA_9'] = trade_df['Close'].ewm(span=9, adjust=False).mean()
    
    if boundary_mode == "Purely Today's Session":
        today_date = trade_df.index[-1].date()
        working_df = trade_df[trade_df.index.date == today_date].copy()
        if len(working_df) < 5:
            working_df = trade_df.tail(40).copy()
    else:
        working_df = trade_df.tail(40).copy()

    # Isolate active vs history rows
    history = working_df.iloc[:-1]
    live_candle = working_df.iloc[-1]
    
    resistance_ceiling = history['High'].max() if not history.empty else live_candle['High']
    support_floor = history['Low'].min() if not history.empty else live_candle['Low']
    
    O, H, L, C = live_candle['Open'], live_candle['High'], live_candle['Low'], live_candle['Close']
    live_ema9 = live_candle['EMA_9']
    
    # Preceding candle arrays for multi-bar identification
    prev_1 = working_df.iloc[-2] if len(working_df) >= 2 else live_candle
    prev_2 = working_df.iloc[-3] if len(working_df) >= 3 else prev_1

    # Volume Shock Engine
    vol_mean = history['Volume'].mean() if not history.empty else 1
    vol_std = history['Volume'].std() if not history.empty else 1
    volume_z_score = (live_candle['Volume'] - vol_mean) / vol_std if vol_std > 0 else 0
    volume_shock_confirmed = volume_z_score >= vol_sigma

    # --- ADVANCED CANDLESTICK SCANNER MODULE ---
    body = abs(C - O)
    total_range = H - L if (H - L) > 0 else 0.01
    upper_wick = H - max(O, C)
    lower_wick = min(O, C) - L
    
    is_doji = body <= (total_range * 0.1)

    detected_pattern = "None"
    pattern_type = "Neutral"
    pattern_weight = "Low"

    # A. Single Candle Math Arrays
    if lower_wick >= (2 * body) and upper_wick <= (0.2 * body) and body > 0:
        if C > O:
            detected_pattern = "🔨 BULLISH HAMMER"
            pattern_type = "Bullish"
        else:
            detected_pattern = "🚨 HANGING MAN"
            pattern_type = "Bearish"
    elif upper_wick >= (2 * body) and lower_wick <= (0.2 * body) and body > 0:
        if C > O:
            detected_pattern = "📐 INVERTED HAMMER"
            pattern_type = "Bullish"
        else:
            detected_pattern = "🏹 SHOOTING STAR"
            pattern_type = "Bearish"
    elif is_doji:
        if lower_wick >= (2 * total_range * 0.3) and upper_wick <= (total_range * 0.1):
            detected_pattern = "🐉 DRAGONFLY DOJI"
            pattern_type = "Bullish"
        elif upper_wick >= (2 * total_range * 0.3) and lower_wick <= (total_range * 0.1):
            detected_pattern = "🪦 GRAVESTONE DOJI"
            pattern_type = "Bearish"

    # B. Double Candle Math Arrays (Tweezers & Engulfing)
    if len(working_df) >= 2:
        prev_O, prev_H, prev_L, prev_C = prev_1['Open'], prev_1['High'], prev_1['Low'], prev_1['Close']
        
        # Tweezer Bottom Identification
        if abs(L - prev_L) <= (L * 0.0005) and prev_C < prev_O and C > O:
            detected_pattern = "🧲 TWEEZER BOTTOM"
            pattern_type = "Bullish"
            pattern_weight = "Medium"
        # Tweezer Top Identification
        elif abs(H - prev_H) <= (H * 0.0005) and prev_C > prev_O and C < O:
            detected_pattern = "🧲 TWEEZER TOP"
            pattern_type = "Bearish"
            pattern_weight = "Medium"

    # C. Triple Candle Series Math Arrays
    if len(working_df) >= 3:
        if C > O and prev_1['Close'] > prev_1['Open'] and prev_2['Close'] > prev_2['Open']:
            if C > prev_1['Close'] and prev_1['Close'] > prev_2['Close']:
                detected_pattern = "⚔️ THREE WHITE SOLDIERS"
                pattern_type = "Bullish"
                pattern_weight = "High"
        elif C < O and prev_1['Close'] < prev_1['Open'] and prev_2['Close'] < prev_2['Open']:
            if C < prev_1['Close'] and prev_1['Close'] < prev_2['Close']:
                detected_pattern = "🐦 THREE BLACK CROWS"
                pattern_type = "Bearish"
                pattern_weight = "High"

    # --- GEOMETRIC RANGE COUPLING ---
    buffer_amt = resistance_ceiling * proximity_buffer_pct
    in_resistance_zone = H >= (resistance_ceiling - buffer_amt)
    in_support_zone = L <= (support_floor + buffer_amt)

    ema_extension_pct = (C - live_ema9) / live_ema9 if live_ema9 > 0 else 0
    is_overextended = ema_extension_pct > max_ema_extension

    # --- PATTERN STRATEGY DECISION MATRIX ---
    status_msg = "⚪ NO-MAN'S LAND (No Trade Zone)"
    analysis_narrative = f"The price is rotating smoothly within structural limits. Active Candlestick Context: <b>{detected_pattern}</b>."
    theme_color = "#1f232a"

    if C > resistance_ceiling:
        if volume_shock_confirmed:
            if is_overextended:
                status_msg = "⚠️ OVEREXTENDED BREAKOUT"
                analysis_narrative = f"Price cleared resistance but is stretched {ema_extension_pct*100:.2f}% away from the 9 EMA. High chasing trap risk."
                theme_color = "#744210"
            elif not higher_tf_is_bullish:
                status_msg = "⚠️ COUNTER-TREND BREAKOUT WARNING"
                analysis_narrative = f"Lower timeframe is breaking out, but the anchor macro trend ({trend_tf}) is Bearish. Expect immediate overhead supply resistance."
                theme_color = "#744210"
            else:
                status_msg = "🚀 PREMIUM MOMENTUM BREAKOUT CONFIRMED"
                analysis_narrative = f"VALID BREAKOUT: Resistance at ₹{resistance_ceiling:.2f} broken on volume shock ({volume_z_score:.1f} σ)."
                theme_color = "#1b4332"
        else:
            status_msg = "⚠️ FALSE BREAKOUT TRAP (Low Volume)"
            analysis_narrative = f"TRAP ALERT: Price crossed above resistance but lacks high-volume institutional backing. Likely a false breakout trap."
            theme_color = "#5c4314"

    # Resistance Rejection Tracker (Short Layout)
    elif in_resistance_zone and C <= resistance_ceiling:
        if pattern_type == "Bearish":
            prefix = "💥 HIGH-CONVICTION" if pattern_weight in ["Medium", "High"] else "⚖️ STANDARD"
            status_msg = f"📉 {prefix} REVERSAL SHORT: {detected_pattern}"
            analysis_narrative = f"The asset rejected your resistance boundary line at ₹{resistance_ceiling:.2f} by printing a clear <b>{detected_pattern}</b> pattern. Target take-profit near support floor floor at ₹{support_floor:.2f}."
            theme_color = "#641e1e"
        else:
            status_msg = "🔍 RESISTANCE PROXIMITY ZONE"
            analysis_narrative = "Price has entered the upper resistance ceiling zone. Waiting for a bearish confirmation layout from your sheet."
            theme_color = "#3d2d2d"

    # Support Bounce Tracker (Buy Layout)
    elif in_support_zone and C >= support_floor:
        if pattern_type == "Bullish":
            prefix = "💥 HIGH-CONVICTION" if pattern_weight in ["Medium", "High"] else "⚖️ STANDARD"
            status_msg = f"🟢 {prefix} REVERSAL BUY: {detected_pattern}"
            analysis_narrative = f"The asset held your support floor wall at ₹{support_floor:.2f} and confirmed it by building a <b>{detected_pattern}</b> trigger. Target take-profit near ceiling line at ₹{resistance_ceiling:.2f}."
            theme_color = "#0a5c36"
        else:
            status_msg = "🔍 SUPPORT PROXIMITY ZONE"
            analysis_narrative = "Price has dipped into your support zone. Waiting for a bullish confirmation layout from your sheet."
            theme_color = "#1d3d2a"

    # Dynamic 9 EMA Trend Continuation Track
    elif abs(C - live_ema9) / live_ema9 <= 0.002:
        if not higher_tf_is_bullish and (C < live_ema9) and pattern_type == "Bearish":
            status_msg = f"📉 TREND SHORT TRIGGERED: {detected_pattern} AT 9 EMA"
            analysis_narrative = f"Trend-Continuation signal confirmed. Price rejected the dynamic 9 EMA resistance track via a <b>{detected_pattern}</b> formation."
            theme_color = "#4d1212"
        elif higher_tf_is_bullish and (C > live_ema9) and pattern_type == "Bullish":
            status_msg = f"🚀 TREND LONG TRIGGERED: {detected_pattern} AT 9 EMA"
            analysis_narrative = f"Trend-Continuation buy signal confirmed. Price bounced from the dynamic 9 EMA track via a <b>{detected_pattern}</b> formation."
            theme_color = "#0f3d21"

    # --- UI RENDERING ENGINE ---
    st.subheader("📊 High-Fidelity Pattern Evaluation Array")
    st.markdown(f"""
    <div style="background-color:{theme_color}; padding:24px; border-radius:10px; border: 1px solid rgba(255,255,255,0.1); margin-bottom:25px;">
        <h3 style="margin-top:0; color:#ffffff; font-family:sans-serif; font-weight:700;">{status_msg}</h3>
        <p style="font-size:16px; color:#f5f5f5; margin-bottom:0; font-family:sans-serif; line-height:1.6;">{analysis_narrative}</p>
    </div>
    """, unsafe_allow_html=True)
    
    d1, d2, d3, d4 = st.columns(4)
    d1.metric(f"Anchor Trend Filter ({trend_tf})", trend_status_text)
    d2.metric("Active Candlestick Profile", "None Detected" if detected_pattern == "None" else detected_pattern)
    d3.metric("Volume Shock Z-Score", f"{volume_z_score:.2f} σ")
    d4.metric("EMA Extension Distance", f"{ema_extension_pct*100:.2f}%")

    # --- RENDER INTERACTIVE PLOTLY CHART ---
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=working_df.index, open=working_df['Open'], high=working_df['High'], low=working_df['Low'], close=working_df['Close'], name="Price Bars"))
    fig.add_trace(go.Scatter(x=working_df.index, y=working_df['EMA_9'], line=dict(color="#3a86ff", width=2), name="9 EMA Line"))
    
    fig.add_shape(type="line", x0=working_df.index[0], y0=resistance_ceiling, x1=working_df.index[-1], y1=resistance_ceiling, line=dict(color="#FF4B4B", width=2, dash="dash"))
    fig.add_shape(type="line", x0=working_df.index[0], y0=support_floor, x1=working_df.index[-1], y1=support_floor, line=dict(color="#2EB82E", width=2, dash="dash"))
    
    fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=550, margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)
