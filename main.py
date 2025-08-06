import json
import time
import random
import logging
import asyncio
import threading
from datetime import datetime, date

import pytz
import pandas as pd
import websockets

from em_api   import get_minute_kline
from signals  import calc_kdj, calc_macd, detect_all_signals

# ---------- 工具函数 ----------
def trade_date_str(cfg_date: str, tz) -> str:
    """返回交易日期字符串；cfg_date='auto' 时取今日"""
    return datetime.now(tz).strftime("%Y%m%d") if cfg_date == "auto" else cfg_date

def in_window(ts: pd.Timestamp, windows, tz) -> bool:
    """判断时间戳是否落在交易时段"""
    if ts.tzinfo is None:
        ts = tz.localize(ts)
    tm = ts.astimezone(tz).time()
    for w in windows:
        s, e = [datetime.strptime(t, "%H:%M").time() for t in w.split("-")]
        if s <= tm <= e:
            return True
    return False

def setup_log(level="INFO"):
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                        format="[%(asctime)s] %(levelname)s: %(message)s",
                        datefmt="%H:%M:%S")

# ---------- WebSocket ----------
latest_payload = {}

async def ws_handler(ws):
    logging.info("WebSocket connected")
    try:
        while True:
            await asyncio.sleep(1)
            if latest_payload:
                await ws.send(json.dumps(latest_payload, default=str))
    except websockets.exceptions.ConnectionClosed:
        logging.info("WebSocket disconnected")

def run_ws_server():
    async def start():
        async with websockets.serve(ws_handler, "0.0.0.0", 8765):
            logging.info("WebSocket server on :8765")
            await asyncio.Future()
    asyncio.run(start())

# ---------- 主流程 ----------
def main():
    global latest_payload

    cfg = json.load(open("config.json", encoding="utf-8"))
    setup_log(cfg["log"].get("level", "INFO"))

    tz = pytz.timezone(cfg["session"]["exchange_tz"])
    trade_date = trade_date_str(cfg["session"]["date"], tz)
    logging.info("Start %s", trade_date)

    # 记录上一条各自指标信号时间，避免日志刷屏
    last_kdj_time  = {c: None for c in cfg["stocks"]}
    last_macd_time = {c: None for c in cfg["stocks"]}

    threading.Thread(target=run_ws_server, daemon=True).start()

    while True:
        now = datetime.now(tz)
        in_sess = in_window(now, cfg["session"]["windows"], tz)

        for code in cfg["stocks"]:
            try:
                df_raw = get_minute_kline(code, trade_date,
                                          timeout=cfg["request"]["timeout_sec"])
                if df_raw.empty:
                    continue

                # 当天、交易时段内
                df_raw["time"] = pd.to_datetime(df_raw["time"]).dt.tz_localize(tz)
                df_day = df_raw[df_raw["time"].dt.date == date.today()]
                df_day = df_day[df_day["time"].apply(
                                lambda t: in_window(t, cfg["session"]["windows"], tz))]
                if df_day.empty:
                    continue

                # 计算指标
                df_day = calc_kdj(df_day,
                                  n=cfg["kdj_param"]["n"],
                                  m1=cfg["kdj_param"]["m1"],
                                  m2=cfg["kdj_param"]["m2"])
                df_day = calc_macd(df_day)
                df_day = detect_all_signals(df_day, code, cfg["thresholds"])

                # ---------- 推送 ----------
                times = []
                latest_kdj  = next((r for _, r in df_day[::-1].iterrows()
                                    if r.kdj_signal),  None)
                latest_macd = next((r for _, r in df_day[::-1].iterrows()
                                    if r.macd_signal), None)
                if latest_kdj is not None:  times.append(latest_kdj.time)
                if latest_macd is not None: times.append(latest_macd.time)
                latest_time = max(times) if times else None
                df_day["realtime"] = df_day["time"] == latest_time

                latest_payload[code] = df_day[[
                    "time","close",
                    "K","D","J",
                    "DIF","DEA","MACD",
                    "kdj_signal","macd_signal",
                    "combo_signal",          # <-- 新列
                    "realtime"
                ]].to_dict("records")

            except Exception as e:
                logging.exception("%s error: %s", code, e)

        # 交易时段内按最小/最大秒随机刷新；非交易时段每 60s
        sleep_sec = (random.uniform(cfg["request"]["interval_sec_min"],
                                    cfg["request"]["interval_sec_max"])
                     if in_sess else 60)
        time.sleep(sleep_sec)

if __name__ == "__main__":
    main()
