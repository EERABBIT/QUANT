import requests
from datetime import datetime
import pandas as pd

def code_to_secid(code: str) -> str:
    return ("1." + code) if code.startswith("6") else ("0." + code)

def get_latest_kline_time(code: str) -> datetime:
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": code_to_secid(code),
        "klt": 1,               # 1分钟线
        "fqt": 0,
        "beg": "20250728",
        "end": "20250728",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56"
    }
    headers = {
        "Referer": "https://quote.eastmoney.com/",
        "User-Agent": "Mozilla/5.0"
    }
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    klines = resp.json().get("data", {}).get("klines", [])
    if not klines:
        raise RuntimeError("未获取到K线数据")
    
    latest_record = klines[-1]
    time_str = latest_record.split(",")[0]
    return pd.to_datetime(time_str)

if __name__ == "__main__":
    stock_code = "600038"
    latest_time = get_latest_kline_time(stock_code)
    now = datetime.now()
    
    diff_sec = int((now - latest_time).total_seconds())
    diff_min = diff_sec // 60
    print(f"🕒 当前系统时间：{now.strftime('%H:%M:%S')}")
    print(f"📈 东方财富最近K线时间：{latest_time.strftime('%H:%M:%S')}")
    print(f"⏱️ 数据延迟：约 {diff_min} 分 {diff_sec % 60} 秒")
