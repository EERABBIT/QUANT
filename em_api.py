# em_api.py
import random
import time
from datetime import datetime
from typing import Optional, Dict, Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# -------------------- 基础配置 --------------------
EM_HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
}

# ---------- 会话 & 重试策略 ----------
def _build_session(
    total_retry: int = 5,
    backoff_factor: float = 0.5,
    status_forcelist: tuple = (429, 500, 502, 503, 504),
) -> requests.Session:
    """
    构造带 Retry 的 requests.Session
    - total_retry : 最大重试次数
    - backoff_factor : 重试退避基数 (指数退避)
    - status_forcelist : 需触发重试的 HTTP 状态码
    """
    session = requests.Session()
    retry = Retry(
        total=total_retry,
        read=total_retry,
        connect=total_retry,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(EM_HEADERS)
    return session


SESSION = _build_session()

# -------------------- 工具函数 --------------------
def _jitter_sleep(base: float = 0.1, fuzz: float = 0.2):
    """
    随机抖动睡眠，用于异常后退避
    base : 基础秒数
    fuzz : 抖动比例 (0~1)
    """
    delta = base * random.uniform(-fuzz, fuzz)
    time.sleep(base + delta)


def code_to_secid(code: str) -> str:
    """6 开头沪市 => 1., 其它（0/3）深市 => 0."""
    return ("1." + code) if code.startswith("6") else ("0." + code)


# -------------------- 1 分钟 K 线 --------------------
def get_minute_kline(
    code: str, date_str: str, timeout: int = 8, max_retry: int = 3
) -> pd.DataFrame:
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
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }

    for attempt in range(1, max_retry + 1):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json().get("data", {})
            klines = data.get("klines", [])
            break
        except Exception as e:
            if attempt == max_retry:
                raise
            _jitter_sleep(0.3 * attempt)  # 退避抖动
    else:  # 理论上不会到这里
        klines = []

    if not klines:
        return pd.DataFrame(
            columns=["time", "open", "close", "high", "low", "volume", "amount"]
        )

    rows = []
    for k in klines:
        p = k.split(",")
        rows.append(
            {
                "time": pd.to_datetime(p[0]),
                "open": float(p[1]),
                "close": float(p[2]),
                "high": float(p[3]),
                "low": float(p[4]),
                "volume": float(p[5]),
                "amount": float(p[6]),
            }
        )
    return pd.DataFrame(rows)


# -------------------- 实时快照 --------------------
def get_realtime_snapshot(
    code: str, timeout: int = 6, max_retry: int = 3
) -> Optional[Dict[str, Any]]:
    """
    东方财富 push2 实时快照（近实时，通常 <2s）
    """
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    fields = ",".join(
        ["f57", "f58", "f43", "f44", "f45", "f46", "f49", "f168", "f50", "f51"]
    )
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": fields,
        "secid": code_to_secid(code),
    }

    for attempt in range(1, max_retry + 1):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            d = r.json().get("data")
            break
        except Exception:
            if attempt == max_retry:
                return None
            _jitter_sleep(0.2 * attempt)
    else:
        d = None

    if not d:
        return None

    # 部分价格字段 *100 返回，这里做一次安全处理
    def f(x): return x / 100 if isinstance(x, (int, float)) else None

    return {
        "code": d.get("f57"),
        "name": d.get("f58"),
        "price": f(d.get("f43")),
        "high": f(d.get("f44")),
        "low": f(d.get("f45")),
        "open": f(d.get("f46")),
        "preclose": f(d.get("f49")),
        "pct_chg": f(d.get("f168")),
        "volume": d.get("f50"),
        "amount": d.get("f51"),
    }
