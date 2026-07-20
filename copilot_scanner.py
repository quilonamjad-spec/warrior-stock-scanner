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
    # Extract scalars safely
    latest_close = df['Close'].iloc[-1].item()
    latest_open  = df['Open'].iloc[-1].item()
    latest_high  = df['High'].iloc[-1].item()
    latest_low   = df['Low'].iloc[-1].item()

    prev_close   = df['Close'].iloc[-2].item()
    prev_open    = df['Open'].iloc[-2].item()
    prev_high    = df['High'].iloc[-2].item()
    prev_low     = df['Low'].iloc[-2].item()

    # Skip if any are NaN
    if any(pd.isna(val) for val in [latest_close, latest_open, latest_high, latest_low,
                                    prev_close, prev_open, prev_high, prev_low]):
        return []

    patterns = []

    # Bullish Engulfing
    if latest_close > latest_open and prev_close < prev_open and latest_close > prev_open:
        patterns.append("Bullish_Engulfing")

    # Bearish Engulfing
    if latest_close < latest_open and prev_close > prev_open and latest_close < prev_open:
        patterns.append("Bearish_Engulfing")

    # Doji
    if abs(latest_close - latest_open) <= (0.1 * (latest_high - latest_low)):
        patterns.append("Doji")

    # Hammer
    if (latest_close > latest_open) and ((latest_low < latest_open*0.98) or (latest_low < latest_close*0.98)):
        if (latest_high - latest_close) < (latest_close - latest_low):
            patterns.append("Hammer")

    # Shooting Star
    if (latest_close < latest_open) and ((latest_high - latest_close) > 2*(latest_close - latest_low)):
        patterns.append("Shooting_Star")

    return patterns



def score_stock(df):
    score = 0
    consensus = 0

    # EMA check
    if df['EMA20'].iloc[-1] > df['EMA50'].iloc[-1]:
        score += SCORING_MATRIX["EMA20_vs_EMA50"]; consensus += 1
    else:
        score -= SCORING_MATRIX["EMA20_vs_EMA50"]

    # RSI check
    if df['RSI'].iloc[-1] > 50:
        score += SCORING_MATRIX["RSI"]; consensus += 1
    else:
        score -= SCORING_MATRIX["RSI"]

    # MACD check
    if df['MACD'].iloc[-1] > 0:
        score += SCORING_MATRIX["MACD"]; consensus += 1
    else:
        score -= SCORING_MATRIX["MACD"]

    # Bollinger check (safe scalar extraction)
    close_val = df['Close'].iloc[-1]
    boll_val = df['Bollinger_Mid'].iloc[-1]
    
    # Ensure scalar
    if isinstance(close_val, pd.Series):
        close_val = close_val.values[-1]
    if isinstance(boll_val, pd.Series):
        boll_val = boll_val.values[-1]
    
    if pd.notna(boll_val):
        close_val = float(close_val)
        boll_val = float(boll_val)
        if close_val > boll_val:
            score += SCORING_MATRIX["Bollinger"]; consensus += 1
        else:
            score -= SCORING_MATRIX["Bollinger"]


    # Candlestick patterns
    patterns = detect_patterns(df)
    for p in patterns:
        score += SCORING_MATRIX[p]

    # Normalize to 100
    normalized_score = round((score / MAX_SCORE) * 100, 2)
    consensus_score = round((consensus / 4) * 100, 2)

    return normalized_score, consensus_score, patterns


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
