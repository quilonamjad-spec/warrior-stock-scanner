import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volume import VolumeWeightedAveragePrice

st.set_page_config(page_title="Day Trading Scanner", layout="wide")
st.title("🚀 Day Trading Scanner - Score & Confidence")

# ================== HELPER FUNCTIONS ==================
def calculate_score_with_history(df):
    df = df.copy()
    
    # Fix MultiIndex columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # Indicators using ta library
    df['EMA20'] = EMAIndicator(close=df['Close'], window=20).ema_indicator()
    df['EMA50'] = EMAIndicator(close=df['Close'], window=50).ema_indicator()
    df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
    
    macd = MACD(close=df['Close'])
    df['MACD'] = macd.macd()
    df['MACD_signal'] = macd.macd_signal()
    df['MACD_hist'] = macd.macd_diff()
    
    df['ADX'] = ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14).adx()
    
    # VWAP
    vwap = VolumeWeightedAveragePrice(
        high=df['High'], low=df['Low'], close=df['Close'], volume=df['Volume']
    )
    df['VWAP'] = vwap.volume_weighted_average_price()
    
    # Drop rows that still have NaN in key columns
    df = df.dropna(subset=['EMA20', 'EMA50', 'RSI', 'MACD_hist', 'ADX', 'VWAP']).copy()
    
    if len(df) < 25:
        raise ValueError("Not enough valid candles after cleaning")
    
    scores = []
    confidences = []
    
    # Start after we have enough clean data
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
        score = round(raw_score * 10, 1)   # Now scaled to roughly -100 to +100
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
    
    # === Restrict chart to only today's data ===
        today = pd.Timestamp.now().normalize()
        history = history[history['Time'].dt.date == today.date()].copy()
        
        if history.empty:  # fallback if market just opened
            history = history.tail(30)
        
        return scores[-1], {
            'Current_Score': round(scores[-1], 1),
            'Confidence': round(confidences[-1], 1),
            'RSI': round(df['RSI'].iloc[-1], 1),
            'VWAP_Dist': round(df['Close'].iloc[-1] - df['VWAP'].iloc[-1], 2),
            'Candles_Used': len(history)
        }, df, history

# ================== SIDEBAR ==================
st.sidebar.header("Settings")
tickers_input = st.sidebar.text_area(
    "Watchlist (one per line)",
    "RELIANCE.NS\nHDFCBANK.NS\nINFY.NS\nTCS.NS\nICICIBANK.NS\nSBIN.NS",
    height=150
)
TICKERS = [t.strip() for t in tickers_input.split("\n") if t.strip()]

interval = st.sidebar.selectbox("Interval", ["5m", "15m"], index=0)
period = st.sidebar.selectbox("Data Period", ["10d", "5d", "1d"], index=0)

# ================== SCAN ==================
if st.sidebar.button("🔄 Run Full Scan", type="primary"):
    with st.spinner("Fetching data..."):
        results = []
        debug_info = []
        
        for ticker in TICKERS:
            try:
                data = yf.download(ticker, period=period, interval=interval, prepost=True, progress=False)
                
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                
                candles = len(data)
                note = f"{ticker}: {candles} candles ({interval})"
                debug_info.append(note)
                
                if candles < 25:
                    continue
                
                score, details, _, score_history = calculate_score_with_history(data)
                
                results.append({
                    'Ticker': ticker.replace('.NS', ''),
                    'Current_Score': score,
                    'Price': round(data['Close'].iloc[-1], 2),
                    'Change%': round((data['Close'].iloc[-1] / data['Close'].iloc[-2] - 1) * 100, 2) if len(data) > 1 else 0,
                    'Details': details,
                    'Score_History': score_history
                })
            except Exception as e:
                debug_info.append(f"{ticker}: Error - {str(e)}")
                continue
        
        st.sidebar.write("### Data Status")
        for info in debug_info:
            st.sidebar.write(info)
        
        if results:
            st.session_state.results = pd.DataFrame(results).sort_values(by='Current_Score', ascending=False)
            st.success(f"✅ Scan complete! {len(results)} stocks analyzed.")
        else:
            st.warning("⚠️ No stocks had enough data.")

# ================== MAIN DISPLAY ==================
if 'results' in st.session_state and not st.session_state.results.empty:
    df_results = st.session_state.results
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🔥 Top 5 Buy Phase")
        for _, r in df_results.head(5).iterrows():
            st.metric(r['Ticker'], f"₹{r['Price']}", f"{r['Change%']}% | Score {r['Current_Score']}")
    
    with col2:
        st.subheader("❄️ Top 5 Sell Phase")
        for _, r in df_results.tail(5).iterrows():
            st.metric(r['Ticker'], f"₹{r['Price']}", f"{r['Change%']}% | Score {r['Current_Score']}")
    
    st.divider()
    
    selected = st.selectbox("Select stock", df_results['Ticker'])
    stock = df_results[df_results['Ticker'] == selected].iloc[0]
    history = stock['Score_History']
    
    score_color = "lime" if stock['Current_Score'] > 30 else "red" if stock['Current_Score'] < -30 else "orange"
    st.markdown(f"""
    <h1 style="text-align: center; color: {score_color}; margin: 20px 0;">
        {selected} — Score: <strong>{stock['Current_Score']}</strong> | 
        Confidence: <strong>{stock['Details']['Confidence']}</strong> | 
        Candles: {stock['Details']['Candles_Used']}
    </h1>
    """, unsafe_allow_html=True)
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(x=history['Time'], y=history['Price'], 
                            name="Price", line=dict(color="yellow", width=2), yaxis="y2"))
    fig.add_trace(go.Scatter(x=history['Time'], y=history['Score'], 
                            name="Score", line=dict(color="white", width=3)))
    fig.add_trace(go.Scatter(x=history['Time'], y=history['Confidence'], 
                            name="Confidence", line=dict(color="cyan", width=3)))
    
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.add_hrect(y0=50, y1=100, fillcolor="green", opacity=0.12, line_width=0)
    fig.add_hrect(y0=-100, y1=-50, fillcolor="red", opacity=0.12, line_width=0)
    
    fig.update_layout(
        height=680,
        title="Price vs Score & Confidence",
        yaxis_title="Score / Confidence",
        yaxis2=dict(title="Price (₹)", overlaying='y', side='right'),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.1)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.json(stock['Details'])

else:
    st.info("Click **Run Full Scan** to start. Check the sidebar for data status.")
