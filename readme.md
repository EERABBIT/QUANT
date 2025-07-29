# KDJ 实时监控项目

> **作用**：拉取东方财富 1 分钟行情，计算 KDJ 指标，推送信号到前端实时可视化。

---

## 📁 目录结构

```
quant/
├── main.py            # 后端入口：拉数据 + WebSocket 推送
├── em_api.py          # 东方财富接口
├── signals.py         # KDJ 计算 & 信号判断
├── config.json        # 全局配置
└── frontend/
    └── index.html     # 前端界面（ECharts）
```

---

## ⚙️ 环境依赖

```bash
conda create -n kdj_env python=3.10 -y
conda activate kdj_env
pip install pandas websockets pytz requests
```

---

## 🚀 快速启动

```bash
# 1. 启动后端
python main.py   # 监听 ws://localhost:8765

# 2. 打开前端
#   方式一：直接双击 frontend/index.html
#   方式二：VS Code Live Server 打开以热刷新
```

---

## 🔧 配置简介（`config.json`）

```json
"session": {
  "exchange_tz": "Asia/Shanghai",           // 行情时区
  "windows": ["09:30-11:30", "13:00-15:00"]
},
"stocks": ["600893"],                        // 监控股票
"thresholds": {
  "default": {                               // 通用阈值
    "buy":  { "k_max": 10, "d_max": 10, "j_max": 0,   "require_turn_up": true  },
    "sell": { "k_min": 90, "d_min": 90, "j_min": 100, "require_turn_down": true }
  },
  "600038": { ... }                          // 个股自定义（可选）
}
```

---

运行后，在浏览器可看到 K、D、J 曲线：

- 红圈 → 历史 BUY/SELL 信号；
- ⭐️ → 当前最新信号。

