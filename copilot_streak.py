import streamlit as st
import pandas as pd
import yfinance as yf
import ta
import json

# -------------------------------
# Utility Functions
# -------------------------------

def fetch_data(ticker, period="6mo", interval="1d"):
    return yf.download(ticker, period=period, interval=interval)

def check_market_trend(index="^NSEI"):
    df = fetch_data(index)
    df["EMA9"] = df["Close"].ewm(span=9).mean()
    df["EMA21"] = df["Close"].ewm(span=21).mean()
    return "Up" if df["EMA9"].iloc[-1] > df["EMA21"].iloc[-1] else "Down"

def first_level_scan(df, market_trend):
    df["EMA9"] = df["Close"].ewm(span=9).mean()
    df["EMA21"] = df["Close"].ewm(span=21).mean()
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    df["VWAP"] = (typical_price * df["Volume"]).cumsum() / df["Volume"].cumsum()
    
    money_flow_multiplier = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / (df["High"] - df["Low"])
    money_flow_volume = money_flow_multiplier * df["Volume"]
    df["ChaikinMF"] = money_flow_volume.cumsum() / df["Volume"].cumsum()

    if market_trend == "Down":
        return (df["EMA9"].iloc[-1] < df["EMA21"].iloc[-1]) and \
               (df["Close"].iloc[-1] < df["High"].rolling(10).max().iloc[-1]) and \
               (df["ChaikinMF"].iloc[-1] < 0) and \
               (df["Volume"].iloc[-1] < df["Volume"].rolling(20).mean().iloc[-1])
    else:  # Market Up
        return (df["Close"].iloc[-1] > df["VWAP"].iloc[-1]) and \
               (df["Volume"].iloc[-1] > df["Volume"].rolling(20).mean().iloc[-1]) and \
               (df["EMA9"].iloc[-1] > df["EMA21"].iloc[-1]) and \
               (df["ChaikinMF"].iloc[-1] > 0)

def scan_and_rank(tickers, market_trend):
    results = []
    for t in tickers:
        df = fetch_data(t)
        if df.empty: 
            continue
        if not first_level_scan(df, market_trend):
            continue

        df["RSI"] = ta.momentum.RSIIndicator(df["Close"]).rsi()
        df["MACD"] = ta.trend.MACD(df["Close"]).macd()

        trade_score = int((df["RSI"].iloc[-1] / 100) * 50 + (df["MACD"].iloc[-1] > 0) * 50)
        confidence_score = int(df["RSI"].iloc[-1])

        results.append({"Ticker": t, "Trade Score": trade_score, "Confidence": confidence_score})

    return pd.DataFrame(results).sort_values(by="Trade Score", ascending=False)

def calculate_scores(df):
    df["EMA9"] = df["Close"].ewm(span=9).mean()
    df["EMA21"] = df["Close"].ewm(span=21).mean()
    df["RSI"] = ta.momentum.RSIIndicator(df["Close"]).rsi().values.ravel()
    df["MACD"] = ta.trend.MACD(df["Close"]).macd().values.ravel()
    df["ADX"] = ta.trend.ADXIndicator(df["High"], df["Low"], df["Close"]).adx().values.ravel()

    df["TradeScore"] = (
        (df["EMA9"] > df["EMA21"]).astype(int) * 20 +
        (df["RSI"] > 60).astype(int) * 20 +
        (df["MACD"] > 0).astype(int) * 20 +
        (df["ADX"] > 25).astype(int) * 20 +
        (df["Close"] > df["Open"]).astype(int) * 20
    )

    df["ConfidenceScore"] = (df["RSI"]/100 * 50) + (df["ADX"]/50 * 50)
    return df

# -------------------------------
# Load NIFTY500 tickers from JSON
# -------------------------------

with open("nifty500.json", "r") as f:
    nifty500_data = json.load(f)
    tickers = nifty500_data["tickers"]

# -------------------------------
# Streamlit UI
# -------------------------------

st.set_page_config(page_title="Adaptive Trading Scanner", layout="wide")
st.title("📊 Adaptive NIFTY500 Trading Assistant")

tab1, tab2 = st.tabs(["Market Scanner", "Continuous Tracking"])

# Tab 1: Scanner
with tab1:
    st.header("Market Scanner")
    market_trend = check_market_trend()
    st.write(f"📈 Market Trend: **{market_trend}**")

    ranked_df = scan_and_rank(tickers, market_trend)

    st.subheader("Ranked Stocks (after first-level scan)")
    st.dataframe(ranked_df)

    st.subheader("Top 5 Picks")
    st.write(ranked_df.head(5))

# Tab 2: Continuous Tracking
with tab2:
    st.header("Trend Dashboard for Committed Trades")
    mode = st.radio("Select Mode", ["Intraday", "Long-term"])

    shortlist = ranked_df["Ticker"].tolist()
    selected = st.multiselect("Pick at least 2 committed trades", shortlist, help="Add custom tickers below")
    custom = st.text_input("Add custom stock symbol (e.g., SBIN.NS)")
    watchlist = selected + ([custom] if custom else [])

    if len(watchlist) >= 2:
        for t in watchlist:
            if mode == "Intraday":
                df = fetch_data(t, period="1d", interval="5m")  # intraday data
            else:
                df = fetch_data(t, period="3mo", interval="1d")  # long-term daily data

            if df.empty: 
                continue

            df = calculate_scores(df)

            st.subheader(f"Trend for {t} ({mode})")
            st.line_chart(df[["TradeScore", "ConfidenceScore"]])

            # Decision summary
            avg_trade = df["TradeScore"].mean()
            avg_conf = df["ConfidenceScore"].mean()
            trend_trade = "Up" if df["TradeScore"].iloc[-1] > df["TradeScore"].iloc[-5] else "Down"
            trend_conf = "Up" if df["ConfidenceScore"].iloc[-1] > df["ConfidenceScore"].iloc[-5] else "Down"

            st.write(f"📊 Avg Trade Score: {avg_trade:.1f}, Trend: {trend_trade}")
            st.write(f"📊 Avg Confidence Score: {avg_conf:.1f}, Trend: {trend_conf}")
