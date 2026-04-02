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

启动对一个或多个股票的实时行情监控和策略信号扫描。

- **接口地址:** `/api/control/start_live`
- **请求方法:** `POST`
- **Content-Type:** `application/json`

**请求参数 (JSON):**

| 参数名 | 类型 | 必填 | 说明 | 示例值 |
| :--- | :--- | :--- | :--- | :--- |
| `stock_code` | string | 否 | 单个股票代码 | `"000001.SZ"` |
| `stock_codes` | string[] | 否 | 多个股票代码 | `["000001.SZ","600036.SH"]` |
| `strategy_id` | string | 否 | 对本次启动股票统一指定单策略 | `"08"` |
| `strategy_ids` | string[] | 否 | 对本次启动股票统一指定多策略 | `["08","34R1"]` |
| `stock_strategy_map` | object | 否 | 每个股票独立策略画像，key=股票代码，value=策略ID数组 | `{"000001.SZ":["08"],"600036.SH":["34R1"]}` |
| `replace_existing` | boolean | 否 | 是否替换当前已运行实盘任务（默认 true） | `true` |

**请求示例:**
```json
{
    "stock_codes": ["000001.SZ", "600036.SH"],
    "stock_strategy_map": {
        "000001.SZ": ["08"],
        "600036.SH": ["34R1", "34R1U"]
    },
    "replace_existing": true
}
```

**响应示例:**
```json
{
    "status": "success",
    "msg": "Live monitoring started for 000001.SZ,600036.SH",
    "started_codes": ["000001.SZ", "600036.SH"],
    "running_codes": ["000001.SZ", "600036.SH"],
    "strategy_profiles": {
        "000001.SZ": ["08"],
        "600036.SH": ["34R1", "34R1U"]
    }
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
| `strategy_id` | string | 否 | 单个策略ID | `"08"` |
| `strategy_ids` | string[] | 否 | 多策略ID | `["08","34R1"]` |
| `stock_codes` | string[] | 否 | 仅对指定股票切换策略，不传则作用于全部运行中的实盘任务 | `["000001.SZ"]` |
| `stock_strategy_map` | object | 否 | 按股票独立切换策略，优先于统一策略参数 | `{"000001.SZ":["08"],"600036.SH":["34R1"]}` |

**请求示例:**
```json
{
    "stock_strategy_map": {
        "000001.SZ": ["08"],
        "600036.SH": ["34R1", "34R1U"]
    }
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
    "backtest_running": false,
    "live_running": true,
    "live_running_codes": ["000001.SZ", "600036.SH"],
    "live_task_count": 2,
    "live_strategy_profiles": {
        "000001.SZ": ["08"],
        "600036.SH": ["34R1", "34R1U"]
    },
    "active_cabinet_type": "LiveCabinet"
}
```

---

## WebSocket 数据流 (可选)

如果调用方需要实时接收策略信号和日志，可以连接 WebSocket。

- **地址:** `ws://localhost:8000/ws`
- **启动实盘命令:** `{"type":"start_simulation","stocks":["000001.SZ","600036.SH"],"stock_strategy_map":{"000001.SZ":["08"],"600036.SH":["34R1"]},"replace_existing":true}`
- **停止实盘命令:** `{"type":"stop_simulation","stocks":["000001.SZ"]}` 或 `{"type":"stop_simulation"}`
- **切策略命令:** `{"type":"switch_strategy","stock_strategy_map":{"000001.SZ":["08"],"600036.SH":["34R1U"]}}`
- **消息类型:**
    - `log`: 系统日志
    - `kline`: 最新 K 线数据
    - `decision`: 最终交易决策 (圣旨)
    - 绝大多数实盘事件会携带 `stock_code` 字段用于多标的区分

---

## 7. Webhook 推送配置（飞书/通用）

在 `config.json` 中通过 `webhook_notification` 配置通知：

- `enabled`: 是否启用
- `event_types`: 需要推送的事件类型白名单
- `webhook_urls`: 通用 webhook 列表（POST JSON）
- `feishu_webhook_url`: 飞书机器人 webhook
- `feishu_secret`: 飞书签名密钥（可选）
- `max_retries` / `retry_backoff_seconds`: 首次发送重试策略
- `persist_failed_events`: 发送失败是否落盘
- `failed_events_file`: 失败事件队列文件（JSONL）
- `failed_retry_interval_seconds`: 失败队列重试间隔
- `failed_retry_batch_size`: 每轮补偿重试最大条数
- `failed_max_retry`: 失败队列单条最大重试次数

---

## 8. Webhook失败队列管理（前台重推）

用于页面手工补偿推送失败记录。

### 8.1 查询失败队列

- **接口地址:** `/api/webhook/failed?limit=200`
- **请求方法:** `GET`

**响应示例:**
```json
{
  "status": "success",
  "count": 2,
  "events": [
    {
      "event_id": "8f329ae71c5b7e11",
      "channel_type": "feishu",
      "event_type": "trade_exec",
      "stock_code": "600036.SH",
      "created_at": "2026-04-01T15:22:11",
      "retries": 1,
      "last_error": "http_error:429"
    }
  ]
}
```

### 8.2 手工重推失败队列

- **接口地址:** `/api/webhook/failed/retry`
- **请求方法:** `POST`
- **Content-Type:** `application/json`

**请求参数 (JSON):**

| 参数名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `event_ids` | string[] | 否 | 指定要重推的记录ID；不传时按队列顺序处理 |
| `limit` | int | 否 | 最多重推条数，默认20 |

### 8.3 清理失败队列

- **接口地址:** `/api/webhook/failed/delete`
- **请求方法:** `POST`
- **Content-Type:** `application/json`

**请求参数 (JSON):**

| 参数名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `event_ids` | string[] | 否 | 仅清理指定ID；不传则清空失败队列 |
