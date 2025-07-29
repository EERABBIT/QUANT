import os
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

from em_api import get_minute_kline
from signals import calc_kdj, detect_signal, detect_all_signals

def in_trading_window(ts: pd.Timestamp, windows, tz):
    if ts.tzinfo is None:
        ts = tz.localize(ts)
    local_time = ts.astimezone(tz)
    t = local_time.time()
    for w in windows:
        s, e = w.split("-")
        s_t = datetime.strptime(s, "%H:%M").time()
        e_t = datetime.strptime(e, "%H:%M").time()
        if s_t <= t <= e_t:
            return True
    return False

def ensure_today_str(cfg_date: str, tz) -> str:
    if cfg_date == "auto":
        return datetime.now(tz).strftime("%Y%m%d")
    return cfg_date

def setup_logger(level="INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    )

latest_data = {}
async def websocket_handler(websocket):
    try:
        logging.info("connection open")
        while True:
            await asyncio.sleep(1)
            if latest_data:
                msg = json.dumps(latest_data, default=str)
                await websocket.send(msg)
    except websockets.exceptions.ConnectionClosed:
        logging.info("connection closed")
    except Exception as e:
        logging.error("connection handler failed: %s", e)

def run_server():
    async def start():
        async with websockets.serve(websocket_handler, "0.0.0.0", 8765):
            logging.info("server listening on 0.0.0.0:8765")
            await asyncio.Future()
    asyncio.run(start())

def main():
    global latest_data

    with open("config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    setup_logger(cfg["log"].get("level", "INFO"))

    tz = pytz.timezone(cfg["session"]["exchange_tz"])
    date_str = ensure_today_str(cfg["session"].get("date", "auto"), tz)

    logging.info("=== start monitor %s ===", date_str)
    logging.info("stocks: %s", cfg["stocks"])

    last_signal_time = {code: None for code in cfg["stocks"]}

    threading.Thread(target=run_server, daemon=True).start()

    while True:
        now = datetime.now(tz)
        in_sess = in_trading_window(now, cfg["session"]["windows"], tz)

        for code in cfg["stocks"]:
            try:
                df = get_minute_kline(code, date_str, timeout=cfg["request"]["timeout_sec"])
                if df.empty:
                    logging.warning("%s no kline data", code)
                    continue

                df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(tz)
                df_today = df[df["time"].dt.date == date.today()].copy()
                df_today = df_today[df_today["time"].apply(lambda t: in_trading_window(t, cfg["session"]["windows"], tz))]

                if df_today.empty:
                    logging.debug("%s no data in session window yet", code)
                    continue

                df_today = calc_kdj(
                    df_today,
                    n=cfg["kdj_param"]["n"],
                    m1=cfg["kdj_param"]["m1"],
                    m2=cfg["kdj_param"]["m2"]
                )

                sig = detect_signal(df_today, code, cfg["thresholds"])
                df_with_signals = detect_all_signals(df_today, code, cfg["thresholds"])

                if sig.side != "NONE":
                    if last_signal_time.get(code) != sig.time:
                        logging.info("[%s] %s @ %s  K=%.2f D=%.2f J=%.2f  (%s)",
                                     code, sig.side, sig.time, sig.k, sig.d, sig.j, sig.reason)
                        last_signal_time[code] = sig.time
                else:
                    logging.info("[%s] @ %s  K=%.2f D=%.2f J=%.2f", code, sig.time, sig.k, sig.d, sig.j)

                # 更新前端数据结构
                df_with_signals["realtime"] = df_with_signals["time"] == sig.time
                df_with_signals["signal"] = df_with_signals.apply(
                    lambda r: sig.side if r["realtime"] else r["signal"], axis=1
                )

                latest_data[code] = df_with_signals[["time", "K", "D", "J", "signal", "realtime"]].to_dict("records")

            except Exception as e:
                logging.exception("code %s error: %s", code, e)

        time.sleep(random.uniform(cfg["request"]["interval_sec_min"], cfg["request"]["interval_sec_max"]) if in_sess else 60)

if __name__ == "__main__":
    main()