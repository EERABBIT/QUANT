import pandas as pd
from collections import namedtuple

Signal = namedtuple("Signal", ["side", "time", "k", "d", "j", "reason"])

def calc_kdj(df: pd.DataFrame, n=9, m1=3, m2=3) -> pd.DataFrame:
    low_list = df["low"].rolling(n, min_periods=1).min()
    high_list = df["high"].rolling(n, min_periods=1).max()
    rsv = (df["close"] - low_list) / (high_list - low_list) * 100
    df["K"] = rsv.ewm(com=m1-1, adjust=False).mean()
    df["D"] = df["K"].ewm(com=m2-1, adjust=False).mean()
    df["J"] = 3 * df["K"] - 2 * df["D"]
    return df

def get_threshold_for(code: str, thresholds: dict) -> dict:
    return thresholds.get(code) or thresholds.get("default", {})

def is_buy_signal(k, d, j, prev_j, threshold: dict) -> bool:
    #cond = (
    #    k+d < threshold["k_max"] + threshold["d_max"] and
    #    j < threshold["j_max"]
    #)
    cond = (
        k < threshold["k_max"] and
        d < threshold["d_max"] and
        j < threshold["j_max"]
    )
    #print(f"[BUY CHECK] k={k:.2f}, d={d:.2f}, j={j:.2f}, cond={cond}")
    if threshold.get("require_turn_up", False) and prev_j is not None:
        cond = cond and (j > prev_j)
    return cond

def is_sell_signal(k, d, j, prev_j, threshold: dict) -> bool:
    cond = (
        k > threshold["k_min"] and
        d > threshold["d_min"] and
        j > threshold["j_min"]
    )
    #print(f"[SELL CHECK] k={k:.2f}, d={d:.2f}, j={j:.2f}, cond={cond}")

    if threshold.get("require_turn_down", False) and prev_j is not None:
        cond = cond and (j < prev_j)
    return cond

def detect_signal(df: pd.DataFrame, code: str, thresholds: dict) -> Signal:
    thresholds = get_threshold_for(code, thresholds)
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2] if len(df) >= 2 else last_row

    k, d, j = last_row["K"], last_row["D"], last_row["J"]
    prev_j = prev_row["J"]
    t = last_row["time"]

    if is_buy_signal(k, d, j, prev_j, thresholds["buy"]):
        return Signal("BUY", t, k, d, j, "low KDJ")

    if is_sell_signal(k, d, j, prev_j, thresholds["sell"]):
        return Signal("SELL", t, k, d, j, "high KDJ")

    return Signal("NONE", t, k, d, j, "")

def detect_all_signals(df: pd.DataFrame, code: str, thresholds: dict) -> pd.DataFrame:
    thresholds = get_threshold_for(code, thresholds)
    signals = []
    prev_j = None

    for i in range(len(df)):
        row = df.iloc[i]
        k, d, j = row["K"], row["D"], row["J"]

        signal = "NONE"
        if pd.notna(k) and pd.notna(d) and pd.notna(j):
            if is_buy_signal(k, d, j, prev_j, thresholds["buy"]):
                signal = "BUY"
            elif is_sell_signal(k, d, j, prev_j, thresholds["sell"]):
                signal = "SELL"

        signals.append(signal)
        prev_j = j

    df = df.copy()
    df["signal"] = signals
    
    return df
