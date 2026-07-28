import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volume import VolumeWeightedAveragePrice
from datetime import datetime

st.set_page_config(page_title="My Stock Watchlist Scanner", layout="wide")
st.title("📈 My Personal Stock Watchlist – Score & Confidence")

# ================== HELPER ==================
def calculate_score_with_history(df):
    df = df.copy()
    
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df['EMA20'] = EMAIndicator(close=df['Close'], window=20).ema_indicator()
    df['EMA50'] = EMAIndicator(close=df['Close'], window=50).ema_indicator()
    df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
    
    macd = MACD(close=df['Close'])
    df['MACD'] = macd.macd()
    df['MACD_signal'] = macd.macd_signal()
    df['MACD_hist'] = macd.macd_diff()
    
    df['ADX'] = ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14).adx()
    
    vwap = VolumeWeightedAveragePrice(
        high=df['High'], low=df['Low'], close=df['Close'], volume=df['Volume']
    )
    df['VWAP'] = vwap.volume_weighted_average_price()
    
    df = df.dropna(subset=['EMA20', 'EMA50', 'RSI', 'MACD_hist', 'ADX', 'VWAP']).copy()
    
    if len(df) < 25:
        raise ValueError("Not enough valid candles")
    
    scores = []
    confidences = []
    start_idx = 25
    
    for i in range(start_idx, len(df)):
        window = df.iloc[:i+1]
        last = window.iloc[-1]
        
        rsi_score = 8 if last['RSI'] < 35 else 4 if last['RSI'] < 45 else -8 if last['RSI'] > 65 else -4 if last['RSI'] > 55 else 0
        macd_score = 9 if last['MACD_hist'] > 0 else -9
        vwap_score = 7 if last['Close'] > last['VWAP'] else -7
        trend_score = 5 if last['EMA20'] > last['EMA50'] else -5
        
        vol_mean = window['Volume'].rolling(20).mean().iloc[-1]
        vol_ratio = last['Volume'] / vol_mean if vol_mean > 0 else 1.0
        
        raw_score = rsi_score*0.2 + macd_score*0.3 + vwap_score*0.25 + trend_score*0.15 + min(vol_ratio*4, 8)*0.1
        score = round(raw_score * 10, 1)
        scores.append(score)
        
        adx_val = last['ADX'] if not pd.isna(last['ADX']) else 20
        signal_align = 1 if (last['MACD_hist'] > 0) == (last['Close'] > last['VWAP']) else 0.6
        confidence = min(100, max(0, adx_val * 2.2 + vol_ratio * 18 + signal_align * 15))
        confidences.append(confidence)
    
    history = pd.DataFrame({
        'Time': df.index[start_idx:],
        'Score': scores,
        'Confidence': confidences,
        'Price': df['Close'].iloc[start_idx:].values
    })
    
    # Keep only today's data for the chart
    today = pd.Timestamp.now().normalize()
    history = history[history['Time'].dt.date == today.date()].copy()
    
    if history.empty:
        history = history.tail(30)
    
    return scores[-1], {
        'Current_Score': round(scores[-1], 1),
        'Confidence': round(confidences[-1], 1),
        'RSI': round(df['RSI'].iloc[-1], 1),
        'VWAP_Dist': round(df['Close'].iloc[-1] - df['VWAP'].iloc[-1], 2),
        'Candles_Used': len(history)
    }, history


def fetch_and_score(ticker, interval, period):
    """Download + calculate for one ticker"""
    data = yf.download(ticker, period=period, interval=interval, prepost=True, progress=False)
    
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    
    if len(data) < 25:
        raise ValueError(f"Only {len(data)} candles available")
    
    score, details, history = calculate_score_with_history(data)
    
    change = 0
    if len(data) > 1:
        change = round((data['Close'].iloc[-1] / data['Close'].iloc[-2] - 1) * 100, 2)
    
    return {
        'Ticker': ticker.replace('.NS', ''),
        'Current_Score': score,
        'Price': round(float(data['Close'].iloc[-1]), 2),
        'Change%': change,
        'Details': details,
        'Score_History': history,
        'Last_Updated': datetime.now().strftime("%H:%M:%S")
    }


# ================== SIDEBAR ==================
st.sidebar.header("⚙️ Your Watchlist")

# Default example stocks
default_tickers = "RELIANCE.NS\nHDFCBANK.NS\nINFY.NS\nTCS.NS\nICICIBANK.NS"

tickers_input = st.sidebar.text_area(
    "Enter stocks (one per line)\nAdd .NS for NSE stocks",
    value=st.session_state.get("watchlist_text", default_tickers),
    height=220
)

interval = st.sidebar.selectbox("Interval", ["5m", "15m", "1m"], index=0)
period = st.sidebar.selectbox("Data Period", ["5d", "10d", "1d"], index=0)

# Parse tickers
TICKERS = [t.strip().upper() for t in tickers_input.split("\n") if t.strip()]

# Auto-refresh option
auto_refresh = st.sidebar.checkbox("🔄 Auto-refresh every 60 seconds", value=False)
if auto_refresh:
    st.sidebar.info("Page will refresh automatically")
    st.markdown(
        """
        <meta http-equiv="refresh" content="60">
        """,
        unsafe_allow_html=True
    )

# ================== LOAD / REFRESH ==================
col_btn1, col_btn2 = st.sidebar.columns(2)

with col_btn1:
    load_btn = st.button("📥 Load / Update All", type="primary", use_container_width=True)

with col_btn2:
    clear_btn = st.button("🗑️ Clear", use_container_width=True)

if clear_btn:
    if "watchlist_data" in st.session_state:
        del st.session_state.watchlist_data
    st.rerun()

if load_btn or "watchlist_data" not in st.session_state:
    if not TICKERS:
        st.warning("Please enter at least one stock symbol.")
    else:
        with st.spinner("Fetching latest data for your stocks..."):
            results = []
            errors = []
            
            for ticker in TICKERS:
                try:
                    # Auto-add .NS if missing (for Indian stocks)
                    if not ticker.endswith((".NS", ".BO")):
                        ticker = ticker + ".NS"
                    
                    result = fetch_and_score(ticker, interval, period)
                    results.append(result)
                except Exception as e:
                    errors.append(f"{ticker}: {str(e)}")
            
            if results:
                st.session_state.watchlist_data = pd.DataFrame(results).sort_values(
                    by='Current_Score', ascending=False
                ).reset_index(drop=True)
                st.session_state.watchlist_text = tickers_input
                st.success(f"✅ Loaded {len(results)} stocks successfully!")
            
            if errors:
                st.sidebar.error("Some failed:")
                for err in errors:
                    st.sidebar.write(err)

# ================== MAIN DISPLAY ==================
if "watchlist_data" in st.session_state and not st.session_state.watchlist_data.empty:
    df = st.session_state.watchlist_data
    
    # ---- Summary Metrics ----
    st.subheader("📊 Your Watchlist Overview")
    
    cols = st.columns(min(5, len(df)))
    for idx, (_, row) in enumerate(df.iterrows()):
        with cols[idx % len(cols)]:
            color = "normal"
            delta_color = "off"
            if row['Current_Score'] > 30:
                delta_color = "normal"
            elif row['Current_Score'] < -30:
                delta_color = "inverse"
            
            st.metric(
                label=row['Ticker'],
                value=f"₹{row['Price']}",
                delta=f"{row['Change%']}% | Score {row['Current_Score']}",
                delta_color=delta_color
            )
    
    st.divider()
    
    # ---- Stock Selector + Refresh ----
    left, right = st.columns([3, 1])
    
    with left:
        selected = st.selectbox(
            "Select stock to view detailed chart",
            options=df['Ticker'].tolist(),
            key="selected_stock"
        )
    
    with right:
        st.write("")  # spacing
        st.write("")
        if st.button("🔄 Refresh This Stock", type="secondary", use_container_width=True):
            with st.spinner(f"Refreshing {selected}..."):
                try:
                    # Find original ticker with .NS
                    original = None
                    for t in TICKERS:
                        clean = t.replace('.NS', '').replace('.BO', '')
                        if clean == selected:
                            original = t if t.endswith(('.NS', '.BO')) else t + ".NS"
                            break
                    if original is None:
                        original = selected + ".NS"
                    
                    updated = fetch_and_score(original, interval, period)
                    
                    # Update the row
                    mask = st.session_state.watchlist_data['Ticker'] == selected
                    for key, value in updated.items():
                        st.session_state.watchlist_data.loc[mask, key] = value
                    
                    # Re-sort
                    st.session_state.watchlist_data = st.session_state.watchlist_data.sort_values(
                        by='Current_Score', ascending=False
                    ).reset_index(drop=True)
                    
                    st.success(f"✅ {selected} updated at {updated['Last_Updated']}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")
    
    # Get current selected data
    stock = df[df['Ticker'] == selected].iloc[0]
    history = stock['Score_History']
    
    # ---- Big Score Header ----
    score_color = "lime" if stock['Current_Score'] > 30 else "red" if stock['Current_Score'] < -30 else "orange"
    
    st.markdown(f"""
    <div style="text-align: center; margin: 20px 0;">
        <h1 style="color: {score_color}; margin-bottom: 5px;">
            {selected} — Score: <strong>{stock['Current_Score']}</strong>
        </h1>
        <h3 style="color: #aaa;">
            Confidence: <strong>{stock['Details']['Confidence']}</strong> &nbsp;|&nbsp;
            RSI: {stock['Details']['RSI']} &nbsp;|&nbsp;
            VWAP Dist: {stock['Details']['VWAP_Dist']} &nbsp;|&nbsp;
            Updated: {stock.get('Last_Updated', '—')}
        </h3>
    </div>
    """, unsafe_allow_html=True)
    
    # ---- Graph ----
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=history['Time'], y=history['Price'],
        name="Price", line=dict(color="#FFD700", width=2.5), yaxis="y2"
    ))
    fig.add_trace(go.Scatter(
        x=history['Time'], y=history['Score'],
        name="Score", line=dict(color="white", width=3)
    ))
    fig.add_trace(go.Scatter(
        x=history['Time'], y=history['Confidence'],
        name="Confidence", line=dict(color="cyan", width=2.5)
    ))
    
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.add_hrect(y0=50, y1=100, fillcolor="green", opacity=0.12, line_width=0)
    fig.add_hrect(y0=-100, y1=-50, fillcolor="red", opacity=0.12, line_width=0)
    
    fig.update_layout(
        height=650,
        title=f"{selected} — Price vs Score & Confidence (Today)",
        yaxis_title="Score / Confidence",
        yaxis2=dict(title="Price (₹)", overlaying='y', side='right'),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.12),
        template="plotly_dark",
        margin=dict(t=80)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # ---- Details ----
    with st.expander("📋 Full Details"):
        st.json(stock['Details'])

else:
    st.info("👈 Enter your stocks in the sidebar and click **Load / Update All** to begin.")
