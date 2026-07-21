import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
import json

# --- PARAMETERS ---
# Load tickers from your JSON file
with open("nifty500.json", "r") as f:
    data = json.load(f)
    TICKERS = data["tickers"]

SCORING_MATRIX = {
    "EMA20_vs_EMA50": 2,
    "RSI": 1,
    "MACD": 1,
    "Bollinger": 1,
    "Bullish_Engulfing": 2,
    "Bearish_Engulfing": -2,
    "Hammer": 2,
    "Shooting_Star": -2,
    "Doji": 0
}
MAX_SCORE = sum(abs(v) for v in SCORING_MATRIX.values())

# --- INDICATORS ---
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(0)

def compute_indicators(df):
    df['EMA20'] = df['Close'].ewm(span=20).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Bollinger_Mid'] = df['Close'].rolling(20).mean()
    return df

# --- PATTERNS ---
def detect_patterns(df):
    if len(df) < 2:
        return []

    # Safe scalar extraction
    latest_close = df['Close'].iloc[-1].item()
    latest_open  = df['Open'].iloc[-1].item()
    latest_high  = df['High'].iloc[-1].item()
    latest_low   = df['Low'].iloc[-1].item()
    prev_close   = df['Close'].iloc[-2].item()
    prev_open    = df['Open'].iloc[-2].item()

    patterns = []
    if latest_close > latest_open and prev_close < prev_open and latest_close > prev_open:
        patterns.append("Bullish_Engulfing")
    if latest_close < latest_open and prev_close > prev_open and latest_close < prev_open:
        patterns.append("Bearish_Engulfing")
    if abs(latest_close - latest_open) <= (0.1 * (latest_high - latest_low)):
        patterns.append("Doji")
    if (latest_close > latest_open) and ((latest_low < latest_open*0.98) or (latest_low < latest_close*0.98)):
        if (latest_high - latest_close) < (latest_close - latest_low):
            patterns.append("Hammer")
    if (latest_close < latest_open) and ((latest_high - latest_close) > 2*(latest_close - latest_low)):
        patterns.append("Shooting_Star")
    return patterns

# --- SCORING ---
def score_stock(df):
    score, consensus = 0, 0
    if df['EMA20'].iloc[-1] > df['EMA50'].iloc[-1]:
        score += SCORING_MATRIX["EMA20_vs_EMA50"]; consensus += 1
    else:
        score -= SCORING_MATRIX["EMA20_vs_EMA50"]
    if df['RSI'].iloc[-1] > 50:
        score += SCORING_MATRIX["RSI"]; consensus += 1
    else:
        score -= SCORING_MATRIX["RSI"]
    if df['MACD'].iloc[-1] > 0:
        score += SCORING_MATRIX["MACD"]; consensus += 1
    else:
        score -= SCORING_MATRIX["MACD"]
        
    close_val = df['Close'].iloc[-1].item()
    boll_val  = df['Bollinger_Mid'].iloc[-1].item()
    
    if pd.notna(boll_val):
        if close_val > boll_val:
            score += SCORING_MATRIX["Bollinger"]; consensus += 1
        else:
            score -= SCORING_MATRIX["Bollinger"]

    patterns = detect_patterns(df)
    for p in patterns:
        score += SCORING_MATRIX[p]
    normalized_score = round((score / MAX_SCORE) * 100, 2)
    consensus_score = round((consensus / 4) * 100, 2)
    return normalized_score, consensus_score, patterns

def scan_market(interval):
    results = []
    for ticker in TICKERS:
        try:
            # intraday data for current day
            df = yf.download(ticker, period="1d", interval=interval)
            df = compute_indicators(df)
            score, consensus, patterns = score_stock(df)
            results.append({
                "Ticker": ticker,
                "Confidence": score,
                "Consensus": consensus,
                "Patterns": ", ".join(patterns)
            })
        except Exception:
            continue
    return pd.DataFrame(results)

# --- STREAMLIT APP ---
st.set_page_config(page_title="Trading Dashboard", layout="wide")
tab1, tab2 = st.tabs(["Scanner", "Tracker"])

with tab1:
    st.header("Market Scanner")
    if st.button("Run Market Scan"):
        df_results = scan_market()
        buy_candidates = df_results[df_results['Confidence'] > 0].sort_values(by="Confidence", ascending=False).head(5)
        sell_candidates = df_results[df_results['Confidence'] < 0].sort_values(by="Confidence", ascending=True).head(5)
        st.subheader("Top 5 BUY Candidates")
        st.dataframe(buy_candidates)
        st.subheader("Top 5 SELL Candidates")
        st.dataframe(sell_candidates)

with tab2:
    st.header("Stock Tracker")

    # Allow both predefined and custom tickers
    selected_tickers = st.multiselect("Choose stocks to track", TICKERS)
    custom_ticker = st.text_input("Or enter a custom ticker (e.g. MYSTOCK.NS)")
    if custom_ticker:
        selected_tickers.append(custom_ticker.upper())

    interval = st.selectbox("Interval", ["5m","15m","30m","1h","1d"], index=0)

    for ticker in selected_tickers:
        df = yf.download(ticker, period="1d", interval=interval)
        df = compute_indicators(df)

        scores, consensuses = [], []
        for i in range(len(df)):
            sub_df = df.iloc[:i+1]
            # Skip if not enough rows for patterns
            if len(sub_df) < 2:
                scores.append(0)
                consensuses.append(0)
                continue
            score, consensus, _ = score_stock(sub_df)
            scores.append(score)
            consensuses.append(consensus)

        st.markdown(f"### {ticker}")
        
        fig, ax = plt.subplots()
        ax.plot(df.index, scores, label="Confidence")
        ax.plot(df.index, consensuses, label="Consensus")
        
        # Horizontal thresholds
        ax.axhline(y=0, color='red', linestyle='--', linewidth=1, label="Confidence = 0")
        ax.axhline(y=50, color='green', linestyle='--', linewidth=1, label="Consensus = 50")
        
        # Highlight strong buy points (Confidence >= 60 & Consensus >= 50)
        for i in range(len(scores)):
            if scores[i] >= 50 and consensuses[i] >= 50:
                ax.scatter(df.index[i], scores[i], color='blue', s=120, marker='o', edgecolors='black', label="Strong Buy" if i == 0 else "")
        
        # Highlight strong sell points (Confidence <= -60 & Consensus >= 50)
            if scores[i] <= -60 and consensuses[i] >= 50:
                ax.scatter(df.index[i], scores[i], color='red', s=120, marker='o', edgecolors='black', label="Strong Sell" if i == 0 else "")
        
        ax.legend()
        st.pyplot(fig)
