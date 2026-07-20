import streamlit as st
import matplotlib.pyplot as plt

st.title("Stock Tracker")

selected_tickers = st.multiselect("Choose stocks to track", ["RELIANCE.NS","TCS.NS","INFY.NS","HDFCBANK.NS"])

for ticker in selected_tickers:
    df = yf.download(ticker, period="1d", interval="15m")
    df = compute_indicators(df)

    scores = []
    consensuses = []
    for i in range(len(df)):
        sub_df = df.iloc[:i+1]
        score, consensus, _ = score_stock(sub_df)
        scores.append(score)
        consensuses.append(consensus)

    st.markdown(f"### {ticker}")
    fig, ax = plt.subplots()
    ax.plot(df.index, scores, label="Confidence")
    ax.plot(df.index, consensuses, label="Consensus")
    ax.legend()
    st.pyplot(fig)
