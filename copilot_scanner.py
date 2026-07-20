import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf

# --- PARAMETERS ---
NIFTY500_TICKERS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]  # Add full Nifty 500 list

# Define scoring matrix (weights)
SCORING_MATRIX = {
    "EMA20_vs_EMA50": 2,
    "RSI": 1,
    "MACD": 1,
    "Bollinger": 1,
    "Bullish_Engulfing": 2,
    "Bearish_Engulfing": -2,
    "Hammer": 2,
    "Shooting_Star": -2,
    "Morning_Star": 2,
    "Evening_Star": -2,
    "Doji": 0,
    "Three_White_Soldiers": 3,
    "Three_Black_Crows": -3
}

MAX_SCORE = sum(abs(v) for v in SCORING_MATRIX.values())

# --- FUNCTIONS ---
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

def detect_patterns(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    patterns = []

    # Bullish Engulfing
    if latest['Close'] > latest['Open'] and prev['Close'] < prev['Open'] and latest['Close'] > prev['Open']:
        patterns.append("Bullish_Engulfing")

    # Bearish Engulfing
    if latest['Close'] < latest['Open'] and prev['Close'] > prev['Open'] and latest['Close'] < prev['Open']:
        patterns.append("Bearish_Engulfing")

    # Doji
    if abs(latest['Close'] - latest['Open']) <= (0.1 * (latest['High'] - latest['Low'])):
        patterns.append("Doji")

    # Hammer
    if (latest['Close'] > latest['Open']) and ((latest['Low'] < latest['Open']*0.98) or (latest['Low'] < latest['Close']*0.98)):
        if (latest['High'] - latest['Close']) < (latest['Close'] - latest['Low']):
            patterns.append("Hammer")

    # Shooting Star
    if (latest['Close'] < latest['Open']) and ((latest['High'] - latest['Close']) > 2*(latest['Close'] - latest['Low'])):
        patterns.append("Shooting_Star")

    return patterns

def score_stock(df):
    score = 0
    consensus = 0

    # Indicators
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

    if df['Close'].iloc[-1] > df['Bollinger_Mid'].iloc[-1]:
        score += SCORING_MATRIX["Bollinger"]; consensus += 1
    else:
        score -= SCORING_MATRIX["Bollinger"]

    # Candlestick patterns
    patterns = detect_patterns(df)
    for p in patterns:
        score += SCORING_MATRIX[p]

    # Normalize to 100
    normalized_score = round((score / MAX_SCORE) * 100, 2)
    consensus_score = round((consensus / 4) * 100, 2)  # 4 indicators used

    return normalized_score, consensus_score, patterns

def scan_market():
    results = []
    for ticker in NIFTY500_TICKERS:
        df = yf.download(ticker, period="3mo", interval="1d")
        df = compute_indicators(df)
        score, consensus, patterns = score_stock(df)
        results.append({"Ticker": ticker, "Confidence": score, "Consensus": consensus, "Patterns": patterns})
    return pd.DataFrame(results)

# --- STREAMLIT DASHBOARD ---
st.set_page_config(page_title="Trading Scanner Dashboard", layout="wide")

st.sidebar.title("Trading Scanner Controls")
scan_button = st.sidebar.button("Run Market Scan")

if scan_button:
    df_results = scan_market()
    df_results = df_results.sort_values(by="Confidence", ascending=False)

    st.subheader("Top 5 BUY Candidates")
    st.dataframe(df_results.head(5))

    st.subheader("Top 5 SELL Candidates")
    st.dataframe(df_results.tail(5))

    # Stock selection
    st.sidebar.subheader("Track Specific Stocks")
    selected_tickers = st.sidebar.multiselect("Choose stocks to track", df_results["Ticker"].tolist())

    for ticker in selected_tickers:
        st.markdown(f"### {ticker} Analysis")
        df = yf.download(ticker, period="3mo", interval="1d")
        df = compute_indicators(df)
        score, consensus, patterns = score_stock(df)

        st.write(f"**Confidence Score:** {score}/100")
        st.write(f"**Consensus Score:** {consensus}/100")
        st.write(f"**Patterns Detected:** {patterns}")

        # Plot candlestick chart
        fig, ax = plt.subplots(figsize=(10,5))
        mpf.plot(df.tail(60), type='candle', mav=(20,50), volume=True, ax=ax)
        st.pyplot(fig)
