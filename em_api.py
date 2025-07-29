# em_api.py
import requests
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any

EM_HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Connection": "close"
}

def code_to_secid(code: str) -> str:
    """6 开头沪市 => 1., 其它（0/3）深市 => 0."""
    return ("1." + code) if code.startswith("6") else ("0." + code)

def get_minute_kline(code: str,
                     date_str: str,
                     timeout: int = 10) -> pd.DataFrame:
    """
    东方财富 push2his 1分钟K线
    - klt: 1 => 1分钟
    - fqt: 0 => 不复权
    注意：EM 返回的时间戳是“该分钟结束时刻”（需自行-1分钟理解延迟）
    """
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": code_to_secid(code),
        "klt": 1,
        "fqt": 0,
        "beg": date_str,
        "end": date_str,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    }
    r = requests.get(url, params=params, headers=EM_HEADERS, timeout=timeout)
    r.raise_for_status()
    data = r.json().get("data", {})
    klines = data.get("klines", [])
    if not klines:
        return pd.DataFrame(columns=["time","open","close","high","low","volume","amount"])

    rows = []
    for k in klines:
        p = k.split(",")
        rows.append({
            "time": pd.to_datetime(p[0]),
            "open": float(p[1]),
            "close": float(p[2]),
            "high": float(p[3]),
            "low": float(p[4]),
            "volume": float(p[5]),
            "amount": float(p[6])
        })
    df = pd.DataFrame(rows)
    return df

def get_realtime_snapshot(code: str,
                          timeout: int = 10) -> Optional[Dict[str, Any]]:
    """
    东方财富 push2 实时快照（近实时，通常<2s）
    """
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    fields = ",".join([
        "f57","f58","f43","f44","f45","f46","f49","f168","f50","f51"
    ])
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": fields,
        "secid": code_to_secid(code)
    }
    r = requests.get(url, params=params, headers=EM_HEADERS, timeout=timeout)
    r.raise_for_status()
    d = r.json().get("data")
    if not d:
        return None
    # 部分价格字段 *100 返回，这里做一次安全处理
    def f(x): return x/100 if isinstance(x, (int, float)) else None
    snap = {
        "code": d.get("f57"),
        "name": d.get("f58"),
        "price": f(d.get("f43")),
        "high": f(d.get("f44")),
        "low": f(d.get("f45")),
        "open": f(d.get("f46")),
        "preclose": f(d.get("f49")),
        "pct_chg": f(d.get("f168")),
        "volume": d.get("f50"),
        "amount": d.get("f51")
    }
    return snap
