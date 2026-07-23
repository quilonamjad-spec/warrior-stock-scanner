import streamlit as st
import yfinance as yf
import pandas as pd
import ta as ta

st.set_page_config(page_title="Day Trading Scanner", layout="wide")
st.title("🚀 Day Trading Scanner - Score & Confidence")

# Sidebar
st.sidebar.header("Settings")
tickers_input = st.sidebar.text_area(
    "Watchlist (one per line)",
    "RELIANCE.NS\nHDFCBANK.NS\nINFY.NS\nTCS.NS\nICICIBANK.NS\nSBIN.NS",
    height=150
)
TICKERS = [t.strip() for t in tickers_input.split("\n") if t.strip()]

interval = st.sidebar.selectbox("Interval", ["5m", "15m"], index=0)
period = st.sidebar.selectbox("Data Period", ["5d", "10d"], index=0)

if st.sidebar.button("🔄 Run Full Scan", type="primary"):
    with st.spinner("Scanning..."):
        results = []
        for ticker in TICKERS:
            try:
                data = yf.download(ticker, period=period, interval=interval, progress=False)
                if len(data) < 40: continue
                
                score, details, df, score_history = calculate_score_with_history(data)
                
                results.append({
                    'Ticker': ticker.replace('.NS', ''),
                    'Current_Score': score,
                    'Price': round(data['Close'].iloc[-1], 2),
                    'Change%': round((data['Close'].iloc[-1] / data['Close'].iloc[-2] - 1) * 100, 2),
                    'Details': details,
                    'Score_History': score_history
                })
            except Exception as e:
                st.error(f"Error with {ticker}: {e}")
                continue
                
        if results:
            st.session_state.results = pd.DataFrame(results).sort_values(by='Current_Score', ascending=False)
        else:
            st.warning("No data returned. Try again.")

# ================== CORE FUNCTIONS ==================
def calculate_vwap(df):
    df = df.copy()
    df['TP'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['TPV'] = df['TP'] * df['Volume']
    df['VWAP'] = df['TPV'].cumsum() / df['Volume'].cumsum()
    return df

def calculate_score_with_history(df):
    df = calculate_vwap(df)
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df['EMA50'] = ta.ema(df['Close'], length=50)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    macd = ta.macd(df['Close'])
    df = pd.concat([df, macd], axis=1)
    df['ADX'] = ta.adx(df['High'], df['Low'], df['Close'], length=14)['ADX_14']
    
    scores = []
    confidences = []
    
    for i in range(40, len(df) + 1):   # start after enough data
        window = df.iloc[:i]
        last = window.iloc[-1]
        
        # Score calculation
        rsi_score = 8 if last['RSI'] < 35 else 4 if last['RSI'] < 45 else -8 if last['RSI'] > 65 else -4 if last['RSI'] > 55 else 0
        macd_score = 9 if last['MACDh_12_26_9'] > 0 else -9
        vwap_score = 7 if last['Close'] > last['VWAP'] else -7
        trend_score = 5 if last['EMA20'] > last['EMA50'] else -5
        vol_ratio = last['Volume'] / window['Volume'].rolling(20).mean().iloc[-1] if window['Volume'].rolling(20).mean().iloc[-1] > 0 else 1
        
        score = round(rsi_score*0.2 + macd_score*0.3 + vwap_score*0.25 + trend_score*0.15 + min(vol_ratio*4, 8)*0.1, 1)
        scores.append(score)
        
        # Confidence
        adx = last['ADX']
        signal_align = 1 if (last['MACDh_12_26_9'] > 0) == (last['Close'] > last['VWAP']) else 0.6
        confidence = min(100, max(0, adx * 2.2 + vol_ratio * 18 + signal_align * 15))
        
        confidences.append(confidence)
    
    history = pd.DataFrame({
        'Time': df.index[40:],
        'Score': scores,
        'Confidence': confidences
    })
    
    current_score = scores[-1]
    current_conf = confidences[-1]
    
    details = {
        'Current_Score': round(current_score, 1),
        'Confidence': round(current_conf, 1),
        'RSI': round(df['RSI'].iloc[-1], 1),
        'VWAP_Dist': round(df['Close'].iloc[-1] - df['VWAP'].iloc[-1], 2)
    }
    
    return current_score, details, df, history

# ================== MAIN UI ==================
if 'results' in st.session_state and not st.session_state.results.empty:
    df_results = st.session_state.results
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🔥 Top 5 Buy")
        for _, r in df_results.head(5).iterrows():
            st.metric(r['Ticker'], f"₹{r['Price']}", f"{r['Change%']}% | Score {r['Current_Score']}")
    
    with col2:
        st.subheader("❄️ Top 5 Sell")
        for _, r in df_results.tail(5).iterrows():
            st.metric(r['Ticker'], f"₹{r['Price']}", f"{r['Change%']}% | Score {r['Current_Score']}")
    
    st.divider()
    
    selected = st.selectbox("Select stock for detailed view", df_results['Ticker'])
    stock = df_results[df_results['Ticker'] == selected].iloc[0]
    history = stock['Score_History']
    
    # Big Score Display
    score_color = "lime" if stock['Current_Score'] > 30 else "red" if stock['Current_Score'] < -30 else "orange"
    st.markdown(f"""
    <h1 style="text-align: center; color: {score_color}; margin: 20px 0;">
        {selected} — Score: <strong>{stock['Current_Score']}</strong> | 
        Confidence: <strong>{stock['Details']['Confidence']}</strong>
    </h1>
    """, unsafe_allow_html=True)
    
    # Single Chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=history['Time'], y=history['Score'], name="Score", line=dict(color="white", width=3)))
    fig.add_trace(go.Scatter(x=history['Time'], y=history['Confidence'], name="Confidence", line=dict(color="cyan", width=3)))
    
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.add_hrect(y0=50, y1=100, fillcolor="green", opacity=0.12, line_width=0)
    fig.add_hrect(y0=-100, y1=-50, fillcolor="red", opacity=0.12, line_width=0)
    
    fig.update_layout(
        height=650,
        title="Score & Confidence Evolution (5-min intervals)",
        yaxis_title="Value",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.1)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.json(stock['Details'])

else:
    st.info("Click **Run Full Scan** to start")
