# 文件：signals.py
import pandas as pd
from collections import namedtuple

Signal = namedtuple("Signal", ["side", "time", "k", "d", "j", "reason"])


def calc_kdj(df: pd.DataFrame, n=9, m1=3, m2=3):
    df = df.copy()
    low_list = df['low'].rolling(window=n, min_periods=1).min()
    high_list = df['high'].rolling(window=n, min_periods=1).max()
    rsv = (df['close'] - low_list) / (high_list - low_list) * 100
    df['K'] = rsv.ewm(alpha=1 / m1, adjust=False).mean()
    df['D'] = df['K'].ewm(alpha=1 / m2, adjust=False).mean()
    df['J'] = 3 * df['K'] - 2 * df['D']
    return df


def detect_signal(df: pd.DataFrame, code: str, thresholds: dict):
    t = thresholds.get(code, thresholds.get("default"))
    row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else row

    k, d, j = row["K"], row["D"], row["J"]
    k_prev, d_prev, j_prev = prev["K"], prev["D"], prev["J"]

    if (
        k < t["buy"]["k_max"] and
        d < t["buy"]["d_max"] and
        j < t["buy"]["j_max"] and
        (not t["buy"].get("require_turn_up") or (k > k_prev and d > d_prev and j > j_prev))
    ):
        return Signal("BUY", row["time"], k, d, j, "threshold and turn_up")

    if (
        k > t["sell"]["k_min"] and
        d > t["sell"]["d_min"] and
        j > t["sell"]["j_min"] and
        (not t["sell"].get("require_turn_down") or (k < k_prev and d < d_prev and j < j_prev))
    ):
        return Signal("SELL", row["time"], k, d, j, "threshold and turn_down")

    return Signal("NONE", row["time"], k, d, j, "")


def detect_all_signals(df: pd.DataFrame, code: str, thresholds: dict) -> pd.DataFrame:
    df = df.copy()
    df["signal"] = ""

    t = thresholds.get(code, thresholds.get("default"))

    for i in range(1, len(df)):
        k, d, j = df.iloc[i]["K"], df.iloc[i]["D"], df.iloc[i]["J"]
        k_prev, d_prev, j_prev = df.iloc[i - 1]["K"], df.iloc[i - 1]["D"], df.iloc[i - 1]["J"]

        #buy_cond = (
        #    k < t["buy"]["k_max"] and
        #    d < t["buy"]["d_max"] and
        #    j < t["buy"]["j_max"]
        #)
        buy_cond = (
            k+d < t["buy"]["k_max"]+ t["buy"]["d_max"] and
            j < t["buy"]["j_max"]
        )

        sell_cond = (
            k > t["sell"]["k_min"] and
            d > t["sell"]["d_min"] and
            j > t["sell"]["j_min"]
        )

        turn_up = k > k_prev and d > d_prev and j > j_prev
        turn_down = k < k_prev and d < d_prev and j < j_prev

        if buy_cond and (not t["buy"].get("require_turn_up") or turn_up):
            df.at[df.index[i], "signal"] = "BUY"
        elif sell_cond and (not t["sell"].get("require_turn_down") or turn_down):
            df.at[df.index[i], "signal"] = "SELL"

    return df
