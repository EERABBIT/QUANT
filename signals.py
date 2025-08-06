import pandas as pd
from collections import namedtuple
from datetime import timedelta

Signal = namedtuple("Signal", ["type", "time", "price", "extra"])

FIVE_MIN = timedelta(minutes=5)

# ---------- 指标计算 ----------
def calc_kdj(df, n=9, m1=3, m2=3):
    low_n  = df["low"].rolling(n, min_periods=1).min()
    high_n = df["high"].rolling(n, min_periods=1).max()
    rsv = (df["close"] - low_n) / (high_n - low_n) * 100
    k = rsv.ewm(alpha=1/m1, adjust=False).mean()
    d = k.ewm(alpha=1/m2, adjust=False).mean()
    j = 3 * k - 2 * d
    df["K"], df["D"], df["J"] = k, d, j
    return df

def calc_macd(df, fast=6, slow=13, signal=5):
    ema_fast = df["close"].ewm(span=fast,  adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd = dif - dea
    df["DIF"], df["DEA"], df["MACD"] = dif, dea, macd
    return df

# ---------- KDJ 信号 ----------
def kdj_signal(row, thr):
    k, d, j = row["K"], row["D"], row["J"]
    buy = (k <= thr["buy"]["k_max"] and d <= thr["buy"]["d_max"] and j <= thr["buy"]["j_max"] and
           (not thr["buy"].get("require_turn_up") or k > d))
    sell = (k >= thr["sell"]["k_min"] and d >= thr["sell"]["d_min"] and j >= thr["sell"]["j_min"] and
            (not thr["sell"].get("require_turn_down") or k < d))
    if buy:  return "BUY"
    if sell: return "SELL"
    return ""

# ---------- MACD 信号（高/低位 + DIF-DEA 拐头） ----------
def macd_band_smooth(df, win=48, k_std=1.0):
    """
    用滚动均值 ± k*std 作为高/低位阈值
    win   : 统计窗口根数
    k_std : 乘数（1 ≈ 68% 覆盖；1.5~2 更宽）
    """
    recent = df.tail(win)
    mean_val = recent[["DIF", "DEA"]].mean().mean()
    std_val  = recent[["DIF", "DEA"]].stack().std()

    high = mean_val + k_std * std_val
    low  = mean_val - k_std * std_val
    return high, low

def macd_turn(prev, cur, ratio=0.5):
    """
    ratio : 拐头幅度占前一根差值比例门槛 (0.2~0.4 常用)
    """
    if prev is None:
        return False, False
    prev_d = prev["DIF"] - prev["DEA"]
    cur_d  = cur["DIF"]  - cur["DEA"]
    diff   = cur_d - prev_d

    up_turn   = prev_d < 0 and diff > 0 and abs(diff) >= ratio * abs(prev_d)
    down_turn = prev_d > 0 and diff < 0 and abs(diff) >= ratio * abs(prev_d)
    return up_turn, down_turn

def macd_signal(cur, prev, bands):
    high, low = bands
    dif, dea = cur["DIF"], cur["DEA"]
    is_high = dif > high and dea > high
    is_low  = dif < low  and dea < low
    up_turn, down_turn = macd_turn(prev, cur)
    if is_low  and up_turn:  return "BUY"
    if is_high and down_turn:return "SELL"
    return ""

# ---------- 批量检测 ----------
def detect_all_signals(df: pd.DataFrame, code: str, thresholds: dict) -> pd.DataFrame:
    thr   = thresholds.get(code, thresholds["default"])
    bands = macd_band_smooth(df)
    prev_row = None
    kdj_col, macd_col = [], []
    last_kdj_time = last_macd_time = None
    combo_col = []

    for _, row in df.iterrows():
        # 单独指标信号
        ksig = kdj_signal (row, thr)
        msig = macd_signal(row, prev_row, bands)
        kdj_col.append(ksig)
        macd_col.append(msig)

        # 记录最近一次时间
        if ksig:  last_kdj_time  = row["time"]
        if msig:  last_macd_time = row["time"]

        # 绿色“共振点”判定
        is_combo = False
        if ksig and last_macd_time and pd.Timedelta(0) <= row["time"] - last_macd_time <= FIVE_MIN:
            is_combo = True
        if msig and last_kdj_time and pd.Timedelta(0) <= row["time"] - last_kdj_time <= FIVE_MIN:
            is_combo = True
        combo_col.append("YES" if is_combo else "")

        prev_row = row

    out = df.copy()
    out["kdj_signal"]   = kdj_col
    out["macd_signal"]  = macd_col
    out["combo_signal"] = combo_col   # 用于股价图绿色点
    return out
