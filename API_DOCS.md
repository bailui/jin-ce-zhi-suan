# 三省六部回测内阁 API 接口文档

本文档描述了如何通过 HTTP 接口与量化交易系统进行交互，适用于 OpenClaw 智能体或其他外部系统。

**基础地址 (Base URL):** `http://localhost:8000`

---

## 1. 策略热更新 (Hot Reload)

在不重启服务的情况下，重新加载 `src/strategies/` 目录下的策略代码。

- **接口地址:** `/api/control/reload_strategies`
- **请求方法:** `POST`
- **Content-Type:** `application/json` (可选，无请求体)

**请求示例 (cURL):**
```bash
curl -X POST http://localhost:8000/api/control/reload_strategies
```

**响应示例 (成功):**
```json
{
    "status": "success",
    "msg": "Successfully reloaded 8 strategies.",
    "strategies": ["01: 三周期共振", "02: 短线弱转强", "08: 神奇九转"]
}
```

---

## 2. 启动历史回测 (Start Backtest)

启动指定股票的历史数据回测任务。

- **接口地址:** `/api/control/start_backtest`
- **请求方法:** `POST`
- **Content-Type:** `application/json`

**请求参数 (JSON):**

| 参数名 | 类型 | 必填 | 说明 | 示例值 |
| :--- | :--- | :--- | :--- | :--- |
| `stock_code` | string | 是 | 股票代码 (Tushare 格式) | `"600036.SH"` |
| `strategy_id` | string | 否 | 策略ID，默认 "all" 运行所有策略 | `"all"` 或 `"08"` |

**请求示例:**
```json
{
    "stock_code": "600036.SH",
    "strategy_id": "all"
}
```

**响应示例:**
```json
{
    "status": "success",
    "msg": "Backtest started for 600036.SH"
}
```

---

## 3. 启动实盘/模拟盘 (Start Live Simulation)

启动对指定股票的实时行情监控和策略信号扫描。

- **接口地址:** `/api/control/start_live`
- **请求方法:** `POST`
- **Content-Type:** `application/json`

**请求参数 (JSON):**

| 参数名 | 类型 | 必填 | 说明 | 示例值 |
| :--- | :--- | :--- | :--- | :--- |
| `stock_code` | string | 是 | 股票代码 | `"000001.SZ"` |

**请求示例:**
```json
{
    "stock_code": "000001.SZ"
}
```

**响应示例:**
```json
{
    "status": "success",
    "msg": "Live monitoring started for 000001.SZ"
}
```

---

## 4. 停止任务 (Stop Task)

停止当前正在运行的回测或实盘任务。

- **接口地址:** `/api/control/stop`
- **请求方法:** `POST`

**请求示例:**
```bash
curl -X POST http://localhost:8000/api/control/stop
```

**响应示例:**
```json
{
    "status": "success",
    "msg": "Task stopped"
}
```

---

## 5. 切换当前策略 (Switch Strategy)

在任务运行过程中，动态切换生效的策略组合。

- **接口地址:** `/api/control/switch_strategy`
- **请求方法:** `POST`
- **Content-Type:** `application/json`

**请求参数 (JSON):**

| 参数名 | 类型 | 必填 | 说明 | 示例值 |
| :--- | :--- | :--- | :--- | :--- |
| `strategy_id` | string | 是 | 策略ID | `"08"` |

**请求示例:**
```json
{
    "strategy_id": "08"
}
```

---

## 6. 获取系统状态 (System Status)

查询当前系统是否正在运行任务。

- **接口地址:** `/api/status`
- **请求方法:** `GET`

**响应示例:**
```json
{
    "is_running": true,
    "active_cabinet_type": "LiveCabinet"
}
```

---

## WebSocket 数据流 (可选)

如果调用方需要实时接收策略信号和日志，可以连接 WebSocket。

- **地址:** `ws://localhost:8000/ws`
- **消息类型:**
    - `log`: 系统日志
    - `kline`: 最新 K 线数据
    - `decision`: 最终交易决策 (圣旨)
