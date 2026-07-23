import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from datetime import datetime

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
                if len(data) < 30: continue
                
                score, details, df, score_history = calculate_score_with_history(data)
                
                results.append({
                    'Ticker': ticker.replace('.NS', ''),
                    'Current_Score': score,
                    'Price': round(data['Close'].iloc[-1], 2),
                    'Change%': round((data['Close'].iloc[-1] / data['Close'].iloc[-2] - 1) * 100, 2),
                    'Details': details,
                    'Data': df,
                    'Score_History': score_history
                })
            except: continue
                
        st.session_state.results = pd.DataFrame(results).sort_values(by='Current_Score', ascending=False)

# ================== CALCULATION WITH HISTORY ==================
def calculate_score_with_history(df):
    df = df.copy()
    df = calculate_vwap(df)
    df['EMA20'] = ta.ema(df['Close'], length=20)
    df['EMA50'] = ta.ema(df['Close'], length=50)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    macd = ta.macd(df['Close'])
    df = pd.concat([df, macd], axis=1)
    df['ADX'] = ta.adx(df['High'], df['Low'], df['Close'], length=14)['ADX_14']
    
    scores = []
    confidences = []
    
    for i in range(30, len(df)+1):
        window = df.iloc[:i]
        
        # Score
        rsi_score = 8 if window['RSI'].iloc[-1] < 35 else 4 if window['RSI'].iloc[-1] < 45 else -8 if window['RSI'].iloc[-1] > 65 else -4 if window['RSI'].iloc[-1] > 55 else 0
        macd_score = 9 if window['MACDh_12_26_9'].iloc[-1] > 0 else -9
        vwap_score = 7 if window['Close'].iloc[-1] > window['VWAP'].iloc[-1] else -7
        trend_score = 5 if window['EMA20'].iloc[-1] > window['EMA50'].iloc[-1] else -5
        
        score = round(rsi_score*0.2 + macd_score*0.3 + vwap_score*0.25 + trend_score*0.15 + min((window['Volume'].iloc[-1]/window['Volume'].rolling(20).mean().iloc[-1])*4, 8)*0.1, 1)
        scores.append(score)
        
        # Confidence (0-100)
        adx = window['ADX'].iloc[-1]
        vol_ratio = window['Volume'].iloc[-1] / window['Volume'].rolling(20).mean().iloc[-1]
        signal_align = 1 if (window['MACDh_12_26_9'].iloc[-1] > 0) == (window['Close'].iloc[-1] > window['VWAP'].iloc[-1]) else 0.5
        confidence = min(100, max(0, (adx * 2) + (vol_ratio * 15) + (signal_align * 20)))
        
        confidences.append(confidence)
    
    df['Score'] = [None]*30 + scores
    df['Confidence'] = [None]*30 + confidences
    
    current_score = scores[-1]
    current_conf = confidences[-1]
    
    details = {
        'Current_Score': round(current_score, 1),
        'Confidence': round(current_conf, 1),
        'RSI': round(df['RSI'].iloc[-1], 1),
        'VWAP_Dist': round(df['Close'].iloc[-1] - df['VWAP'].iloc[-1], 2)
    }
    
    return current_score, details, df, pd.DataFrame({
        'Time': df.index[30:],
        'Score': scores,
        'Confidence': confidences
    })

def calculate_vwap(df):
    df['TP'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['TPV'] = df['TP'] * df['Volume']
    df['VWAP'] = df['TPV'].cumsum() / df['Volume'].cumsum()
    return df

# ================== DISPLAY ==================
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
    
    selected = st.selectbox("Select stock", df_results['Ticker'])
    stock = df_results[df_results['Ticker'] == selected].iloc[0]
    history = stock['Score_History']
    
    # Current Score Display
    score_color = "lime" if stock['Current_Score'] > 50 else "red" if stock['Current_Score'] < -50 else "orange"
    st.markdown(f"""
    <h1 style="text-align: center; color: {score_color}; margin: 10px;">
        {selected} — Score: <strong>{stock['Current_Score']}</strong> | Confidence: <strong>{stock['Details']['Confidence']}</strong>
    </h1>
    """, unsafe_allow_html=True)
    
    # Single Chart: Score + Confidence
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(x=history['Time'], y=history['Score'], 
                            name="Score", line=dict(color="white", width=3)))
    fig.add_trace(go.Scatter(x=history['Time'], y=history['Confidence'], 
                            name="Confidence", line=dict(color="cyan", width=3)))
    
    # Zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Zero")
    
    # Buy / Sell zones
    fig.add_hrect(y0=50, y1=100, fillcolor="green", opacity=0.1, line_width=0)
    fig.add_hrect(y0=-100, y1=-50, fillcolor="red", opacity=0.1, line_width=0)
    
    fig.update_layout(
        height=600,
        title="Score Evolution & Market Confidence (Every 5 min)",
        yaxis_title="Value",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.json(stock['Details'])

else:
    st.info("Click 'Run Full Scan' to start")
