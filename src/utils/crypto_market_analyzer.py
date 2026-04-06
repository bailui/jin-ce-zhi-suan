import json
import os
from datetime import datetime, timedelta

import pandas as pd

from src.utils.binance_provider import BinanceProvider
from src.utils.indicators import Indicators


class CryptoMarketAnalyzer:
    def __init__(self, provider=None):
        self.provider = provider or BinanceProvider()
        self._last_optimizer_data = {}
        self._last_optimizer_at = None

    def _get_optimizer_best(self):
        now = datetime.utcnow()
        if self._last_optimizer_at and (now - self._last_optimizer_at) < timedelta(minutes=5):
            return self._last_optimizer_data
        
        file_path = os.path.join("data", "optimizer", "crypto_optimizer_latest.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._last_optimizer_data = data.get("best_by_strategy", {})
                    self._last_optimizer_at = now
                    return self._last_optimizer_data
            except:
                pass
        return {}

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _fetch(self, symbol, interval, days):
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        return self.provider.fetch_kline_data(symbol, start_time, end_time, interval=interval)

    def _fmt_price(self, value):
        n = self._safe_float(value, None)
        if n is None:
            return "--"
        if n >= 1000:
            return f"{n:,.2f}"
        if n >= 1:
            return f"{n:,.4f}"
        return f"{n:,.6f}"

    def _build_trade_state(self, action, current_price, entry_low=None, entry_high=None, stop_loss=None):
        px = self._safe_float(current_price, 0.0)
        stop = self._safe_float(stop_loss, None)
        low = self._safe_float(entry_low, None)
        high = self._safe_float(entry_high, None)
        near_stop_ratio = 0.0035

        if action == "做多" and stop is not None:
            if px <= stop:
                return {
                    "state_code": "invalidated",
                    "state_label": "信号失效",
                    "state_detail": "现价已经跌破止损位，这笔多单计划失效。",
                }
            if (px - stop) / max(px, 1e-9) <= near_stop_ratio:
                return {
                    "state_code": "near_stop",
                    "state_label": "接近止损",
                    "state_detail": "价格距离止损位过近，现在追单的盈亏比不理想。",
                }
            if low is not None and high is not None:
                if px < low:
                    return {
                        "state_code": "waiting_entry",
                        "state_label": "未到开仓区",
                        "state_detail": "价格还没回踩到多单参考区，先等触发再动手。",
                    }
                if low <= px <= high:
                    return {
                        "state_code": "in_entry_zone",
                        "state_label": "已进入开仓区",
                        "state_detail": "价格已经回到多单参考区，可以考虑分批试单。",
                    }
                return {
                    "state_code": "passed_entry",
                    "state_label": "已穿越开仓区",
                    "state_detail": "价格已经离开原计划入场区，追价前先重新评估盈亏比。",
                }

        if action == "做空" and stop is not None:
            if px >= stop:
                return {
                    "state_code": "invalidated",
                    "state_label": "信号失效",
                    "state_detail": "现价已经碰到止损位，这笔空单计划失效。",
                }
            if (stop - px) / max(px, 1e-9) <= near_stop_ratio:
                return {
                    "state_code": "near_stop",
                    "state_label": "接近止损",
                    "state_detail": "价格离空单止损位很近，现在追空的性价比偏低。",
                }
            if low is not None and high is not None:
                if px < low:
                    return {
                        "state_code": "waiting_entry",
                        "state_label": "未到开仓区",
                        "state_detail": "价格还没反弹到空单参考区，先等触发再动手。",
                    }
                if low <= px <= high:
                    return {
                        "state_code": "in_entry_zone",
                        "state_label": "已进入开仓区",
                        "state_detail": "价格已经进入空单参考区，可以考虑轻仓分批试空。",
                    }
                return {
                    "state_code": "passed_entry",
                    "state_label": "已穿越开仓区",
                    "state_detail": "价格已经越过原计划空单入场区，追空前先重算风险回报。",
                }

        return {
            "state_code": "waiting_signal",
            "state_label": "等待触发",
            "state_detail": "当前更适合观察，等突破或回踩确认后再执行。",
        }

    def _build_trade_plan(self, direction, close, ema21, ema55, atr_pct, position_pct):
        px = max(self._safe_float(close, 0.0), 1e-9)
        ema_fast = self._safe_float(ema21, px)
        ema_slow = self._safe_float(ema55, px)
        atr_ratio = max(self._safe_float(atr_pct, 0.015), 0.008)
        pullback = max(atr_ratio * 0.6, 0.004)
        tp1_ratio = max(atr_ratio * 1.4, 0.018)
        tp2_ratio = max(atr_ratio * 2.4, 0.032)
        stop_ratio = max(atr_ratio * 1.1, 0.012)
        base_stop = max(ema_slow, px * (1 - stop_ratio))

        if str(direction).upper() in {"LONG", "LIGHT_LONG"}:
            low = min(px, ema_fast * (1 + 0.002))
            high = max(px * (1 - pullback), ema_fast * (1 - 0.001))
            entry_zone = f"{self._fmt_price(min(low, high))} - {self._fmt_price(max(low, high))}"
            stop_loss = base_stop
            trade_state = self._build_trade_state("做多", px, entry_low=min(low, high), entry_high=max(low, high), stop_loss=stop_loss)
            return {
                "action": "做多",
                "bias": "顺势分批开多",
                "entry_zone": entry_zone,
                "entry_low": round(min(low, high), 8),
                "entry_high": round(max(low, high), 8),
                "stop_loss": self._fmt_price(stop_loss),
                "take_profit_1": self._fmt_price(px * (1 + tp1_ratio)),
                "take_profit_2": self._fmt_price(px * (1 + tp2_ratio)),
                "position_pct": round(self._safe_float(position_pct), 1),
                "leverage": 1 if position_pct < 35 else (2 if position_pct < 60 else 3),
                **trade_state,
            }

        if str(direction).upper() in {"SHORT", "LIGHT_SHORT"}:
            rebound = max(atr_ratio * 0.6, 0.004)
            low = min(px * (1 + rebound), ema_fast * (1 + 0.001))
            high = max(px, ema_fast * (1 + 0.004))
            stop_loss = min(px * (1 + stop_ratio), max(ema_slow, ema_fast) * (1 + 0.003))
            trade_state = self._build_trade_state("做空", px, entry_low=min(low, high), entry_high=max(low, high), stop_loss=stop_loss)
            return {
                "action": "做空",
                "bias": "反弹承压再分批试空",
                "entry_zone": f"{self._fmt_price(min(low, high))} - {self._fmt_price(max(low, high))}",
                "entry_low": round(min(low, high), 8),
                "entry_high": round(max(low, high), 8),
                "stop_loss": self._fmt_price(stop_loss),
                "take_profit_1": self._fmt_price(px * (1 - tp1_ratio)),
                "take_profit_2": self._fmt_price(px * (1 - tp2_ratio)),
                "position_pct": round(self._safe_float(position_pct), 1),
                "leverage": 1 if position_pct < 35 else (2 if position_pct < 55 else 3),
                **trade_state,
            }

        breakout = px * (1 + max(atr_ratio * 0.7, 0.01))
        breakdown = px * (1 - max(atr_ratio * 0.7, 0.01))
        return {
            "action": "观望",
            "bias": "等待确认后再动手",
            "entry_zone": f"上破 {self._fmt_price(breakout)} 再考虑试单",
            "stop_loss": self._fmt_price(base_stop),
            "take_profit_1": self._fmt_price(px * (1 + max(tp1_ratio, 0.02))),
            "take_profit_2": self._fmt_price(px * (1 + max(tp2_ratio, 0.04))),
            "defensive_line": self._fmt_price(breakdown),
            "position_pct": round(self._safe_float(position_pct), 1),
            "leverage": 1,
            **self._build_trade_state("观望", px, stop_loss=base_stop),
        }

    def detect_market_regime(self, df_1h, df_4h):
        """
        职业级市场环境探测：判断当前是【趋势】、【震荡】还是【恐慌】。
        """
        if len(df_1h) < 60: return "UNKNOWN", 50
        
        # 1. 波动率压缩探测 (Squeeze)
        df_1h['ma20'] = df_1h['close'].rolling(20).mean()
        df_1h['std20'] = df_1h['close'].rolling(20).std()
        df_1h['upper'] = df_1h['ma20'] + 2 * df_1h['std20']
        df_1h['lower'] = df_1h['ma20'] - 2 * df_1h['std20']
        bandwidth = (df_1h['upper'] - df_1h['lower']) / df_1h['ma20']
        curr_bandwidth = bandwidth.iloc[-1]
        avg_bandwidth = bandwidth.tail(100).mean()
        
        # 2. 动量强度 (ADX 简化版)
        diff = df_1h['close'].diff()
        pos_move = diff.where(diff > 0, 0).rolling(14).mean()
        neg_move = (-diff).where(diff < 0, 0).rolling(14).mean()
        adx_sim = abs(pos_move - neg_move) / (pos_move + neg_move + 1e-9)
        curr_adx = adx_sim.iloc[-1]

        # 逻辑判断
        if curr_bandwidth < avg_bandwidth * 0.6:
            return "SQUEEZE", 40 # 极度压缩，变盘在前，EMA失效，胜率下调
        if curr_adx > 0.3:
            # 强趋势
            direction = "BULL_TREND" if pos_move.iloc[-1] > neg_move.iloc[-1] else "BEAR_TREND"
            return direction, 80 # 强趋势中 EMA 胜率极高
        if curr_bandwidth > avg_bandwidth * 1.5:
            return "VOLATILE", 30 # 宽幅震荡，极易洗盘，观望为主
            
        return "CHOPPY", 50 # 普通震荡

    def analyze_symbol(self, symbol):
        # ... (existing code for fetching df_1m, df_1h, df_4h, df_1d)
        df_1h = self._fetch(symbol, "1h", 90)
        df_4h = self._fetch(symbol, "4h", 240)
        df_1d = self._fetch(symbol, "1d", 400)
        if df_1h.empty or df_4h.empty or df_1d.empty:
            return {
                "symbol": symbol,
                "direction": "WAIT",
                "confidence": 0,
                "position_pct": 0,
                "risk_level": "HIGH",
                "risk_hint": "历史K线不足，先不要跟单。",
                "summary": "数据不足",
                "metrics": {},
                "top_strategies": [],
            }

        df_1h = df_1h.copy()
        df_4h = df_4h.copy()
        df_1d = df_1d.copy()

        df_1h["ema21"] = Indicators.EMA(df_1h["close"], 21)
        df_1h["ema55"] = Indicators.EMA(df_1h["close"], 55)
        df_1h["rsi14"] = Indicators.RSI(df_1h["close"], 14)
        df_1h["atr14"] = Indicators.ATR(df_1h["high"], df_1h["low"], df_1h["close"], 14)
        df_1h["cmf20"] = Indicators.CMF(df_1h, 20)
        df_1h["vwap"] = Indicators.VWAP(df_1h)
        df_1h["vol_avg"] = df_1h["vol"].rolling(20).mean()
        
        df_4h["ema21"] = Indicators.EMA(df_4h["close"], 21)
        df_4h["ema55"] = Indicators.EMA(df_4h["close"], 55)
        df_4h["ema200"] = Indicators.EMA(df_4h["close"], 200)
        df_4h["rsi14"] = Indicators.RSI(df_4h["close"], 14)
        df_4h["atr14"] = Indicators.ATR(df_4h["high"], df_4h["low"], df_4h["close"], 14)
        df_1d["ema20"] = Indicators.EMA(df_1d["close"], 20)
        df_1d["ema50"] = Indicators.EMA(df_1d["close"], 50)
        df_1d["rsi14"] = Indicators.RSI(df_1d["close"], 14)

        df_1h = df_1h.dropna().reset_index(drop=True)
        df_4h = df_4h.dropna().reset_index(drop=True)
        df_1d = df_1d.dropna().reset_index(drop=True)
        if len(df_1h) < 80 or len(df_4h) < 50 or len(df_1d) < 50:
            return {
                "symbol": symbol,
                "direction": "WAIT",
                "confidence": 0,
                "position_pct": 0,
                "risk_level": "HIGH",
                "risk_hint": "有效指标不足，等待更多数据。",
                "summary": "指标不足",
                "metrics": {},
                "top_strategies": [],
            }

        h1 = df_1h.iloc[-1]
        h4 = df_4h.iloc[-1]
        d1 = df_1d.iloc[-1]
        d1_prev = df_1d.iloc[-2]

        close = self._safe_float(h1["close"])
        ret_7d = (self._safe_float(df_1d["close"].iloc[-1]) / max(self._safe_float(df_1d["close"].iloc[-8]), 1e-9)) - 1 if len(df_1d) >= 8 else 0.0
        ret_30d = (self._safe_float(df_1d["close"].iloc[-1]) / max(self._safe_float(df_1d["close"].iloc[-31]), 1e-9)) - 1 if len(df_1d) >= 31 else 0.0
        atr_pct = self._safe_float(h1["atr14"]) / max(close, 1e-9)

        score = 0
        h1_ema_bull = self._safe_float(h1["close"]) > self._safe_float(h1["ema21"]) > self._safe_float(h1["ema55"])
        h4_ema_bull = self._safe_float(h4["close"]) > self._safe_float(h4["ema21"]) > self._safe_float(h4["ema55"])
        d1_ema_bull = self._safe_float(d1["close"]) > self._safe_float(d1["ema20"]) > self._safe_float(d1["ema50"])

        # 1. 市场环境加权 (核心优化：顺势而为)
        regime, regime_conf = self.detect_market_regime(df_1h, df_4h)
        is_structural_bull = float(h4["close"]) > float(h4.get("ema200", 0))
        if is_structural_bull:
            score += 15 # 宏观牛市阶段，给予更高基础分
        else:
            score -= 10 # 宏观熊市阶段，交易频率与仓位应收紧

        if regime in {"BULL_TREND", "BEAR_TREND"}:
            score += 10 # 趋势市加分
        elif regime == "SQUEEZE":
            score -= 15 # 压缩市极易变盘，下调胜率，等待突破
        elif regime == "VOLATILE":
            score -= 20 # 异常波动期，防守为主

        # 1.1 资金流与大户踪迹 (CMF & VWAP)
        cmf = self._safe_float(h1.get("cmf20", 0))
        vwap = self._safe_float(h1.get("vwap", 0))
        if cmf > 0.1 and close > vwap:
            score += 15 # 明显的资金流入 + 成本支撑 (机构吸筹迹象)
        elif cmf < -0.1 and close < vwap:
            score -= 15 # 资金流出 + 成本压制 (庄家出货)

        # 1.2 出货预警 (Volume Climax)
        vol_avg = float(h1.get("vol_avg", 0))
        if vol_avg > 0 and float(h1.get("vol", 0)) > vol_avg * 2.2:
            if float(h1["rsi14"]) > 75:
                score -= 30 # 高位放巨量 + RSI超买 (经典的庄家派发顶部信号)
                summary = "警惕！放量滞涨，可能存在庄家派发。"

        # 2. 趋势一致性 (三周期共振是高胜率的核心)
        if h1_ema_bull: score += 10
        if h4_ema_bull: score += 15
        if d1_ema_bull: score += 15
        if h1_ema_bull and h4_ema_bull and d1_ema_bull:
            score += 15 # 三周期全多头共振额外加分

        # 2. 价格与均线乖离率 (防止追高)
        bias_h1 = (self._safe_float(h1["close"]) - self._safe_float(h1["ema21"])) / max(self._safe_float(h1["ema21"]), 1e-9)
        if 0 < bias_h1 < 0.03:
            score += 10 # 处于合理回踩区间，胜率更高
        elif bias_h1 > 0.08:
            score -= 15 # 乖离过大，有回撤风险

        # 3. 强弱与动量
        if ret_7d > 0.05: score += 10 # 强势品种
        if 50 < self._safe_float(h1["rsi14"]) < 65: score += 10 # 处于强势起点

        # 4. 波动率风控
        if atr_pct > 0.05:
            score -= 10 # 波动过大，容易扫损
        elif 0.01 < atr_pct < 0.03:
            score += 5 # 波动适中，趋势稳定性好

        # 5. 空头过滤 (防止反向开仓)
        if self._safe_float(h1["close"]) < self._safe_float(h1["ema55"]):
            score = min(score, 45) # H1跌破55线，多单置信度封顶

        score = max(0, min(100, int(round(score))))
        
        # 确定风险等级与信号汇总
        if score >= 85:
            direction = "LONG"
            position_pct = 80
            risk_level = "LOW"
            summary = "顶级趋势共振，机构级多头结构，胜率极高。"
            risk_hint = "多周期完美共振，极高置信度机会，建议严格执行止损即可。"
            top_strategies = ["16", "15", "14", "10", "11"]
        elif score >= 65:
            direction = "LONG"
            position_pct = 50
            risk_level = "MEDIUM"
            summary = "中短期趋势向上，可轻仓顺势。"
            risk_hint = "趋势占优，但需注意短线乖离，分批入场更稳健。"
            top_strategies = ["16", "15", "10", "12"]
        elif score >= 40:
            direction = "WAIT"
            position_pct = 0
            risk_level = "MEDIUM"
            summary = "多空均衡，无明显博弈优势。"
            risk_hint = "没有形成高胜率单边结构，优先等确认。"
            top_strategies = ["13", "15"]
        elif (
            self._safe_float(h1["close"]) < self._safe_float(h1["ema21"])
            and self._safe_float(h4["close"]) < self._safe_float(h4["ema21"])
            and self._safe_float(d1["close"]) < self._safe_float(d1["ema20"])
        ):
            direction = "SHORT"
            position_pct = 40
            risk_level = "HIGH"
            summary = "全周期空头压制，结构性走弱。"
            risk_hint = "空头有效，但合约只建议低杠杆，止损必须硬执行。"
            top_strategies = ["12", "13"]
        else:
            direction = "DEFENSIVE"
            position_pct = 0
            risk_level = "HIGH"
            summary = "趋势不明，防守为上。"
            risk_hint = "当前环境不稳，建议保留现金。"
            top_strategies = ["13"]

        return {
            "symbol": symbol,
            "direction": direction,
            "confidence": score,
            "position_pct": position_pct,
            "risk_level": risk_level,
            "risk_hint": risk_hint,
            "summary": summary,
            "metrics": {
                "price": round(close, 4),
                "ret_7d": round(ret_7d, 4),
                "ret_30d": round(ret_30d, 4),
                "atr_pct": round(atr_pct, 4),
                "h1_rsi": round(self._safe_float(h1["rsi14"]), 2),
                "h4_rsi": round(self._safe_float(h4["rsi14"]), 2),
                "d1_rsi": round(self._safe_float(d1["rsi14"]), 2),
                "updated_at": str(h1.get("dt", "")),
            },
            "top_strategies": top_strategies,
            "trade_plan": self._build_trade_plan(direction, close, h1.get("ema21"), h1.get("ema55"), atr_pct, position_pct),
        }

    def check_signal_status(self, event, current_price):
        px = self._safe_float(current_price, 0.0)
        action = str(event.get("action", "")).strip()
        low = self._safe_float(event.get("entry_low"), None)
        high = self._safe_float(event.get("entry_high"), None)
        stop = self._safe_float(event.get("stop_loss"), None)
        event_time = event.get("time")

        # Expiry check (24 hours)
        if event_time:
            try:
                dt = datetime.strptime(event_time, "%Y-%m-%d %H:%M:%S")
                if datetime.now() - dt > timedelta(hours=24):
                    return {"state_code": "expired", "state_label": "已过期", "state_detail": "信号已发布超过24小时，参考价值降低。"}
            except:
                pass

        # Parse stop_loss if it's a string like "67,004.82"
        if isinstance(event.get("stop_loss"), str):
            try:
                stop = float(event.get("stop_loss").replace(",", ""))
            except:
                pass

        if not action or px <= 0:
            return {"state_code": "unknown", "state_label": "未知状态"}

        if action == "做多":
            if stop is not None and px <= stop:
                return {"state_code": "invalidated", "state_label": "已失效", "state_detail": "价格已跌破止损位。"}
            if low is not None and high is not None:
                if low <= px <= high:
                    return {"state_code": "in_entry_zone", "state_label": "已触发", "state_detail": "价格当前正处于多单开仓区。"}
                if px > high:
                    return {"state_code": "passed_entry", "state_label": "已穿越", "state_detail": "价格已向上穿过多单开仓区。"}
                return {"state_code": "waiting_entry", "state_label": "等待触发", "state_detail": "价格尚未回调至多单开仓区。"}

        if action == "做空":
            if stop is not None and px >= stop:
                return {"state_code": "invalidated", "state_label": "已失效", "state_detail": "价格已突破止损位。"}
            if low is not None and high is not None:
                if low <= px <= high:
                    return {"state_code": "in_entry_zone", "state_label": "已触发", "state_detail": "价格当前正处于空单开仓区。"}
                if px < low:
                    return {"state_code": "passed_entry", "state_label": "已穿越", "state_detail": "价格已向下穿过空单开仓区。"}
                return {"state_code": "waiting_entry", "state_label": "等待触发", "state_detail": "价格尚未反弹至空单开仓区。"}

        return {"state_code": "waiting_signal", "state_label": "等待触发"}

    def audit_performance(self):
        """
        实时审计：对过去历史信号的胜率进行真实核算。
        """
        file_path = os.path.join("data", "crypto_signal_history.json")
        if not os.path.exists(file_path):
            return {"win_rate": 0, "sample_size": 0, "drift": 0}
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                history = data.get("history", [])
                if not history: return {"win_rate": 0, "sample_size": 0, "drift": 0}
                
                # 统计最近 30 条已分出结果的信号
                resolved = [h for h in history if h.get("state_code") in {"invalidated", "passed_entry"}]
                if not resolved: return {"win_rate": 0, "sample_size": 0, "drift": 0}
                
                # passed_entry 视为胜 (触发了开仓区并穿过)，invalidated 视为负
                wins = len([h for h in resolved if h.get("state_code") == "passed_entry"])
                win_rate = round(wins / len(resolved) * 100, 1)
                
                # 计算预测置信度与实际胜率的偏差 (Drift)
                avg_conf = sum(h.get("confidence", 0) for h in resolved) / len(resolved)
                drift = round(win_rate - avg_conf, 1)
                
                return {
                    "win_rate": win_rate, 
                    "sample_size": len(resolved), 
                    "drift": drift,
                    "health": "STABLE" if abs(drift) < 15 else ("RISKY" if drift < -15 else "CONSERVATIVE")
                }
        except:
            return {"win_rate": 0, "sample_size": 0, "drift": 0}

    def build_panel(self, symbols=None):
        pairs = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "PEPEUSDT", "ORDIUSDT"]
        items = [self.analyze_symbol(symbol) for symbol in pairs]
        leader = max(items, key=lambda item: item.get("confidence", 0)) if items else None
        market_score = round(sum(item.get("confidence", 0) for item in items) / len(items), 1) if items else 0.0
        
        # Optimizer Integration
        best_params = self._get_optimizer_best()
        optimizer_note = ""
        if best_params:
            for sid, res in best_params.items():
                if res:
                    optimizer_note = f"当前主力策略基于最新优化参数运行：{res.get('strategy_id')} 评分 {res.get('score')}。"
                    break

        if market_score >= 70:
            market_regime = "风险偏好扩张"
        elif market_score >= 50:
            market_regime = "结构性偏多"
        elif market_score >= 35:
            market_regime = "震荡观察"
        else:
            market_regime = "防守优先"
        # Audit Integration
        audit = self.audit_performance()
        
        # Determine Market Sentiment based on Regime
        regimes = [self.detect_market_regime(self._fetch(s, "1h", 60), self._fetch(s, "4h", 60))[0] for s in pairs]
        dominant_regime = max(set(regimes), key=regimes.count) if regimes else "CHOPPY"

        return {
            "status": "success",
            "updated_at": datetime.utcnow().isoformat(),
            "market_score": market_score,
            "market_regime": market_regime,
            "dominant_regime": dominant_regime,
            "audit": audit,
            "leader": leader,
            "items": items,
            "optimizer_note": optimizer_note,
            "engine": {
                "version": "crypto-panel-v2",
                "notes": [
                    f"当前市场主导环境：{dominant_regime}。",
                    f"近期策略胜率审计：{audit.get('win_rate')}% (样本量 {audit.get('sample_size')})。",
                    "风险模型已切换至自适应 ATR 止损，策略优化器每 60 分钟自动寻优一次。"
                ],
            },
        }
