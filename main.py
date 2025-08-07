import json, time, random, logging, asyncio, threading, subprocess, argparse
from datetime import datetime, date

import pytz, pandas as pd, websockets

from em_api   import get_minute_kline
from signals  import calc_kdj, calc_macd, detect_all_signals

# ---------- 系统通知 ----------
def mac_notify(title, msg, enabled=True):
    if enabled:
        subprocess.run(["osascript", "-e",
            f'display notification "{msg}" with title "{title}"'])

# ---------- 工具 ----------
def trade_date_str(cfg_date, tz):
    return datetime.now(tz).strftime("%Y%m%d") if cfg_date == "auto" else cfg_date

def in_window(ts, windows, tz):
    if ts.tzinfo is None:
        ts = tz.localize(ts)
    tm = ts.astimezone(tz).time()
    return any(datetime.strptime(s,"%H:%M").time() <= tm <= datetime.strptime(e,"%H:%M").time()
               for s,e in (w.split("-") for w in windows))

def setup_log(lv="INFO"):
    logging.basicConfig(level=getattr(logging, lv.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")

# ---------- WebSocket ----------
latest_payload = {}
def run_ws(port):
    async def handler(ws):
        try:
            while True:
                await asyncio.sleep(1)
                if latest_payload:
                    await ws.send(json.dumps(latest_payload, default=str))
        except websockets.exceptions.ConnectionClosed:
            pass

    async def start():
        async with websockets.serve(handler, "0.0.0.0", port):
            logging.info("WebSocket server on :%d", port)
            await asyncio.Future()
    asyncio.run(start())

# ---------- 主 ----------
def main():
    # -------- 解析命令行 --------
    p = argparse.ArgumentParser()
    p.add_argument("--code", help="单只股票代码")
    p.add_argument("--name", help="股票中文名，可选")
    p.add_argument("--port", type=int, help="WebSocket 端口")
    args = p.parse_args()

    # -------- 读取配置 --------
    cfg = json.load(open("config.json", encoding="utf-8"))
    setup_log(cfg["log"].get("level", "INFO"))
    notify_mac = cfg.get("notify", {}).get("mac", True)

    # ---- 股票映射 & 端口 ----
    if args.code:                     # CLI 优先
        stock_map = {args.code: args.name or args.code}
    else:
        stock_map = cfg["stocks"]

    ws_port = args.port or cfg.get("port", 8765)

    tz = pytz.timezone(cfg["session"]["exchange_tz"])
    trade_date = trade_date_str(cfg["session"]["date"], tz)

    codes = list(stock_map.keys())
    threading.Thread(target=run_ws, args=(ws_port,), daemon=True).start()

    last_kdj_time  = {c: None for c in codes}
    last_macd_time = {c: None for c in codes}
    last_combo_time= {c: None for c in codes}

    while True:
        now = datetime.now(tz)
        in_sess = in_window(now, cfg["session"]["windows"], tz)

        for code in codes:
            try:
                df_raw = get_minute_kline(code, trade_date,
                                          timeout=cfg["request"]["timeout_sec"])
                if df_raw.empty:
                    continue

                df_raw["time"] = pd.to_datetime(df_raw["time"]).dt.tz_localize(tz)
                df_day = df_raw[df_raw["time"].dt.date == date.today()]
                df_day = df_day[df_day["time"].apply(
                        lambda t: in_window(t, cfg["session"]["windows"], tz))]
                if df_day.empty:
                    continue

                df_day = calc_kdj(df_day, **cfg["kdj_param"])
                df_day = calc_macd(df_day)
                # detect_all_signals 内部已 thresholds.get(code, default)
                df_day = detect_all_signals(df_day, code, cfg["thresholds"])

                # 最新信号
                latest_kdj  = next((r for _,r in df_day[::-1].iterrows()
                                    if r.kdj_signal), None)
                latest_macd = next((r for _,r in df_day[::-1].iterrows()
                                    if r.macd_signal), None)
                latest_combo= next((r for _,r in df_day[::-1].iterrows()
                                    if r.combo_signal), None)

                name = stock_map[code]

                # 通知
                if notify_mac:
                #    if latest_kdj is not None and latest_kdj.time != last_kdj_time[code]:
                #        mac_notify(f"{code} {name} KDJ {latest_kdj.kdj_signal}",
                #                   f"K={latest_kdj.K:.2f} D={latest_kdj.D:.2f} J={latest_kdj.J:.2f}")
                #        last_kdj_time[code] = latest_kdj.time
                #    if latest_macd is not None and latest_macd.time != last_macd_time[code]:
                #        mac_notify(f"{code} {name} MACD {latest_macd.macd_signal}",
                #                   f"DIF={latest_macd.DIF:.3f} DEA={latest_macd.DEA:.3f}")
                #        last_macd_time[code] = latest_macd.time
                    if latest_combo is not None and latest_combo.time != last_combo_time[code]:
                        mac_notify(f"{code} {name} 联合信号",
                                   f"Price={latest_combo.close:.2f}")
                        last_combo_time[code] = latest_combo.time

                # realtime 标记
                times=[]
                if latest_kdj  is not None: times.append(latest_kdj.time)
                if latest_macd is not None: times.append(latest_macd.time)
                if latest_combo is not None: times.append(latest_combo.time)
                latest_time = max(times) if times else None
                df_day["realtime"] = df_day["time"] == latest_time
                df_day["name"] = name

                latest_payload[code] = df_day[[
                    "time","close","K","D","J","DIF","DEA","MACD",
                    "kdj_signal","macd_signal","combo_signal",
                    "realtime","name"
                ]].to_dict("records")

            except Exception as e:
                logging.exception("%s error: %s", code, e)

        time.sleep(random.uniform(cfg["request"]["interval_sec_min"],
                                  cfg["request"]["interval_sec_max"]) if in_sess else 60)

if __name__ == "__main__":
    main()
