# src/strategies/implemented_strategies.py
from src.strategies.base_strategy import BaseStrategy
from src.utils.indicators import Indicators
import pandas as pd
import numpy as np
import math
from src.utils.runtime_params import get_value

class BaseImplementedStrategy(BaseStrategy):
    """
    Base class for implemented strategies with common utilities.
    """
    def __init__(self, strategy_id, name, trigger_timeframe="1min"):
        super().__init__(strategy_id)
        self.name = name
        self.trigger_timeframe = trigger_timeframe
        self.bars_held = {} # Code -> Count of bars held
        self.entry_price = {} # Code -> Entry Price
        self.highest_high = {} # Code -> Highest High since entry
        self.trailing_stop_level = {} # Code -> Trailing Stop Price
        self.current_cash = 0.0
        self.available_cash = 0.0
        self.total_value = 0.0
        self.last_price = 0.0

    def preprocess(self, kline):
        code = kline['code']
        self.last_price = float(kline['close'])
        if code in self.positions and self.positions[code] > 0:
            self.bars_held[code] = self.bars_held.get(code, 0) + 1
        else:
            self.bars_held[code] = 0
            self.highest_high[code] = 0.0
            self.trailing_stop_level[code] = 0.0
        
        if not hasattr(self, 'data_history'): self.data_history = {}
        if not isinstance(self.data_history, dict): self.data_history = {}
            
        if code not in self.data_history: self.data_history[code] = pd.DataFrame()
        self.data_history[code] = pd.concat([self.data_history[code], pd.DataFrame([kline])], ignore_index=True).tail(5000)
        return self.data_history[code]

    def create_exit_signal(self, kline, qty, reason):
        return {
            'strategy_id': self.id,
            'code': kline['code'],
            'dt': kline['dt'],
            'direction': 'SELL',
            'price': float(kline['close']),
            'qty': qty,
            'reason': reason
        }

    def _cfg(self, key, default):
        own = get_value(f"strategy_params.{self.id}.{key}", None)
        if own is not None:
            return own
        common = get_value(f"strategy_params.common.{key}", None)
        return common if common is not None else default

    def _qty(self):
        asset_class = str(get_value("system.asset_class", "equity")).strip().lower()
        mode = str(self._cfg("order_qty_mode", "fixed")).strip().lower()
        fixed_qty = float(self._cfg("order_qty", 1000))
        if mode != "cash_pct":
            return max(0.0, fixed_qty)
        cash = float(
            getattr(self, "current_cash", None)
            if getattr(self, "current_cash", None) is not None
            else getattr(self, "available_cash", getattr(self, "cash", 0.0))
        )
        pct = float(self._cfg("order_cash_pct", 0.1))
        price = float(self.last_price or 0.0)
        if pct > 1:
            pct = pct / 100.0
        pct = max(0.0, min(1.0, pct))
        if cash <= 0 or price <= 0 or pct <= 0:
            return 0
        if asset_class == "crypto":
            step = float(get_value("trading_rules.qty_step", 0.0001))
            min_qty = float(get_value("trading_rules.min_order_qty", step))
            raw_qty = (cash * pct) / price
            if step > 0:
                stepped_qty = math.floor((raw_qty / step) + 1e-9) * step
            else:
                stepped_qty = raw_qty
            if stepped_qty < min_qty:
                return 0.0
            return float(round(stepped_qty, 8))
        raw_qty = int((cash * pct) // price)
        lot_size = 100
        lot_qty = (raw_qty // lot_size) * lot_size
        return max(0, lot_qty)

    def set_backtest_context(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        if "current_cash" in kwargs and "available_cash" not in kwargs:
            self.available_cash = kwargs.get("current_cash")
        if "available_cash" in kwargs and "current_cash" not in kwargs:
            self.current_cash = kwargs.get("available_cash")
        if "total_value" not in kwargs:
            self.total_value = float(self.current_cash or self.available_cash or 0.0)

class Strategy00(BaseImplementedStrategy):
    def __init__(self):
        super().__init__("00", "00 - 长期持有策略", trigger_timeframe="D")
        self.entered = {}
        self.final_bar_dt = None

    def on_bar(self, kline):
        code = kline['code']
        self.last_price = float(kline['close'])
        qty = self.positions.get(code, 0)
        current_dt = pd.to_datetime(kline['dt'])
        if qty <= 0 and not self.entered.get(code, False):
            buy_qty = self._qty()
            if buy_qty <= 0: return None
            self.entered[code] = True
            return {
                'strategy_id': self.id, 'code': code, 'dt': kline['dt'],
                'direction': 'BUY', 'price': kline['close'], 'qty': buy_qty,
                'stop_loss': 0.0, 'take_profit': None
            }
        if qty > 0 and self.final_bar_dt is not None and current_dt >= pd.to_datetime(self.final_bar_dt):
            return self.create_exit_signal(kline, qty, "Backtest Last Bar Exit")
        return None

class Strategy10(BaseImplementedStrategy):
    def __init__(self):
        super().__init__("10", "10 - 均线引力趋势追踪", trigger_timeframe="1h")

    def on_bar(self, kline):
        df = self.preprocess(kline)
        code = kline["code"]
        if len(df) < 100: return None
        df_1h = Indicators.resample(df, "1h")
        if len(df_1h) < 60: return None
        df_1h["ema21"] = Indicators.EMA(df_1h["close"], 21)
        df_1h["ema55"] = Indicators.EMA(df_1h["close"], 55)
        df_1h["atr"] = Indicators.ATR(df_1h, 14)
        df_1h = df_1h.dropna().reset_index(drop=True)
        if len(df_1h) < 2: return None
        curr, prev = df_1h.iloc[-1], df_1h.iloc[-2]
        qty = float(self.positions.get(code, 0.0) or 0.0)
        if qty > 0:
            self.highest_high[code] = max(self.highest_high.get(code, 0.0), float(curr["close"]))
            trail = float(self.highest_high[code] - curr["atr"] * 3.5)
            self.trailing_stop_level[code] = max(self.trailing_stop_level.get(code, 0.0), trail)
            if float(curr["close"]) <= self.trailing_stop_level[code] or curr["ema21"] < curr["ema55"]:
                return self.create_exit_signal(kline, qty, "Exit")
            return None
        if prev["ema21"] <= prev["ema55"] and curr["ema21"] > curr["ema55"]:
            buy_qty = self._qty()
            if buy_qty <= 0: return None
            stop = float(curr["close"] - curr["atr"] * 2.5)
            self.trailing_stop_level[code] = stop
            self.highest_high[code] = float(curr["close"])
            return {'strategy_id': self.id, 'code': code, 'dt': kline['dt'], 'direction': 'BUY', 'price': float(kline['close']), 'qty': buy_qty, 'stop_loss': stop, 'take_profit': None}
        return None

class Strategy11(BaseImplementedStrategy):
    def __init__(self):
        super().__init__("11", "11 - 唐奇安通道破位捕捉", trigger_timeframe="1h")

    def on_bar(self, kline):
        df = self.preprocess(kline)
        code = kline["code"]
        if len(df) < 100: return None
        df_1h = Indicators.resample(df, "1h")
        if len(df_1h) < 30: return None
        df_1h["ema200"] = Indicators.EMA(df_1h["close"], 200)
        df_1h = df_1h.dropna().reset_index(drop=True)
        if len(df_1h) < 21: return None
        curr = df_1h.iloc[-1]
        qty = float(self.positions.get(code, 0.0) or 0.0)
        breakout_h = float(df_1h["high"].iloc[-21:-1].max())
        exit_l = float(df_1h["low"].iloc[-11:-1].min())
        if qty > 0:
            if float(curr["close"]) < exit_l:
                return self.create_exit_signal(kline, qty, "Exit")
            return None
        if float(curr["close"]) > breakout_h:
            buy_qty = self._qty()
            if buy_qty <= 0: return None
            return {'strategy_id': self.id, 'code': code, 'dt': kline['dt'], 'direction': 'BUY', 'price': float(kline['close']), 'qty': buy_qty, 'stop_loss': exit_l, 'take_profit': None}
        return None

class Strategy12(BaseImplementedStrategy):
    def __init__(self):
        super().__init__("12", "12 - ATR 波动率自适应", trigger_timeframe="15min")

    def on_bar(self, kline):
        df = self.preprocess(kline)
        code = kline["code"]
        if len(df) < 100: return None
        df_15m = Indicators.resample(df, "15min")
        if len(df_15m) < 30: return None
        df_15m["ema20"] = Indicators.EMA(df_15m["close"], 20)
        df_15m["atr"] = Indicators.ATR(df_15m, 20)
        df_15m["kc_upper"] = df_15m["ema20"] + (df_15m["atr"] * 2.0)
        df_15m["kc_lower"] = df_15m["ema20"] - (df_15m["atr"] * 2.0)
        df_15m = df_15m.dropna().reset_index(drop=True)
        if len(df_15m) < 2: return None
        curr = df_15m.iloc[-1]
        qty = float(self.positions.get(code, 0.0) or 0.0)
        if qty > 0:
            if float(curr["close"]) < float(curr["ema20"]): return self.create_exit_signal(kline, qty, "Exit")
            return None
        if float(curr["close"]) > float(curr["kc_upper"]):
            buy_qty = self._qty()
            if buy_qty <= 0: return None
            return {'strategy_id': self.id, 'code': code, 'dt': kline['dt'], 'direction': 'BUY', 'price': float(kline['close']), 'qty': buy_qty, 'stop_loss': float(curr["kc_lower"]), 'take_profit': None}
        return None

class Strategy13(BaseImplementedStrategy):
    def __init__(self):
        super().__init__("13", "13 - 布林极限均值回归", trigger_timeframe="1h")

    def on_bar(self, kline):
        df = self.preprocess(kline)
        code = kline["code"]
        if len(df) < 150: return None
        df_1h = Indicators.resample(df, "1h")
        if len(df_1h) < 40: return None
        df_1h["rsi"] = Indicators.RSI(df_1h["close"], 14)
        up, mid, lw = Indicators.BollingerBands(df_1h["close"], 20, 2.0)
        df_1h["bb_mid"], df_1h["bb_lower"] = mid, lw
        df_1h["atr"] = Indicators.ATR(df_1h, 14)
        df_1h = df_1h.dropna().reset_index(drop=True)
        if len(df_1h) < 2: return None
        curr, prev = df_1h.iloc[-1], df_1h.iloc[-2]
        qty = float(self.positions.get(code, 0.0) or 0.0)
        if qty > 0:
            if float(curr["close"]) >= float(curr["bb_mid"]) or float(curr["rsi"]) > 65:
                return self.create_exit_signal(kline, qty, "TakeProfit")
            return None
        if float(curr["rsi"]) < 35 and float(curr["rsi"]) > float(prev["rsi"]):
            buy_qty = self._qty()
            if buy_qty <= 0: return None
            return {'strategy_id': self.id, 'code': code, 'dt': kline['dt'], 'direction': 'BUY', 'price': float(kline['close']), 'qty': buy_qty, 'stop_loss': float(curr["close"] - curr["atr"] * 1.5), 'take_profit': float(curr["bb_mid"])}
        return None

class Strategy14(BaseImplementedStrategy):
    def __init__(self):
        super().__init__("14", "14 - 多维共振动量引擎", trigger_timeframe="4h")

    def on_bar(self, kline):
        df = self.preprocess(kline)
        code = kline["code"]
        if len(df) < 200: return None
        df_4h = Indicators.resample(df, "4h")
        if len(df_4h) < 40: return None
        df_4h["ema20"] = Indicators.EMA(df_4h["close"], 20)
        df_4h["rsi"] = Indicators.RSI(df_4h["close"], 14)
        df_4h["atr"] = Indicators.ATR(df_4h, 14)
        df_4h = df_4h.dropna().reset_index(drop=True)
        if len(df_4h) < 2: return None
        curr = df_4h.iloc[-1]
        qty = float(self.positions.get(code, 0.0) or 0.0)
        score = (40 if float(curr["close"]) > float(curr["ema20"]) else 0) + (30 if float(curr["rsi"]) > 52 else 0) + (30 if float(curr["vol"]) > df_4h["vol"].rolling(10).mean().iloc[-1] else 0)
        if qty > 0:
            if score < 30: return self.create_exit_signal(kline, qty, "Exit")
            return None
        if score >= 75:
            buy_qty = self._qty()
            if buy_qty <= 0: return None
            return {'strategy_id': self.id, 'code': code, 'dt': kline['dt'], 'direction': 'BUY', 'price': float(kline['close']), 'qty': buy_qty, 'stop_loss': float(curr["close"] - curr["atr"] * 2.5), 'take_profit': None}
        return None

class Strategy15(BaseImplementedStrategy):
    def __init__(self):
        super().__init__("15", "15 - 闪电高频剥头皮 (Scalp)", trigger_timeframe="15min")

    def on_bar(self, kline):
        df = self.preprocess(kline)
        code = kline["code"]
        if len(df) < 60: return None
        df_15m = Indicators.resample(df, "15min")
        if len(df_15m) < 20: return None
        df_15m["ema9"] = Indicators.EMA(df_15m["close"], 9)
        df_15m["ema21"] = Indicators.EMA(df_15m["close"], 21)
        df_15m["atr"] = Indicators.ATR(df_15m, 14)
        df_15m = df_15m.dropna().reset_index(drop=True)
        if len(df_15m) < 2: return None
        curr = df_15m.iloc[-1]
        qty = float(self.positions.get(code, 0.0) or 0.0)
        if qty > 0:
            if float(curr["close"]) < float(curr["ema21"]): return self.create_exit_signal(kline, qty, "Exit")
            return None
        if float(curr["close"]) > float(curr["ema9"]) > float(curr["ema21"]):
            buy_qty = self._qty()
            if buy_qty <= 0: return None
            return {'strategy_id': self.id, 'code': code, 'dt': kline['dt'], 'direction': 'BUY', 'price': float(kline['close']), 'qty': buy_qty, 'stop_loss': float(curr["close"] - curr["atr"] * 1.5), 'take_profit': float(curr["close"] + curr["atr"] * 3.0)}
        return None

class Strategy16(BaseImplementedStrategy):
    def __init__(self):
        super().__init__("16", "16 - 机构博弈庄家足迹", trigger_timeframe="4h")

    def on_bar(self, kline):
        df = self.preprocess(kline)
        code = kline["code"]
        if len(df) < 300: return None
        df_4h = Indicators.resample(df, "4h")
        if len(df_4h) < 40: return None
        df_4h["cmf"] = Indicators.CMF(df_4h, 20)
        df_4h["rsi"] = Indicators.RSI(df_4h["close"], 14)
        df_4h["atr"] = Indicators.ATR(df_4h, 14)
        df_4h = df_4h.dropna().reset_index(drop=True)
        if len(df_4h) < 2: return None
        curr = df_4h.iloc[-1]
        qty = float(self.positions.get(code, 0.0) or 0.0)
        if qty > 0:
            self.highest_high[code] = max(self.highest_high.get(code, 0.0), float(curr["close"]))
            if float(curr["close"]) < float(self.highest_high[code] - curr["atr"] * 4.0):
                return self.create_exit_signal(kline, qty, "Exit")
            return None
        if float(curr["cmf"]) > 0.02 or float(curr["rsi"]) < 25:
            buy_qty = self._qty()
            if buy_qty <= 0: return None
            return {'strategy_id': self.id, 'code': code, 'dt': kline['dt'], 'direction': 'BUY', 'price': float(kline['close']), 'qty': buy_qty, 'stop_loss': float(curr["close"] - curr["atr"] * 2.0), 'take_profit': None}
        return None

class Strategy17(BaseImplementedStrategy):
    def __init__(self):
        super().__init__("17", "17 - BTC 动量突破专业版", trigger_timeframe="15min")

    def on_bar(self, kline):
        df = self.preprocess(kline)
        code = kline["code"]
        if len(df) < 60: return None
        df_15m = Indicators.resample(df, "15min")
        if len(df_15m) < 30: return None
        df_15m["ema10"] = Indicators.EMA(df_15m["close"], 10)
        df_15m["ema20"] = Indicators.EMA(df_15m["close"], 20)
        df_15m["rsi"] = Indicators.RSI(df_15m["close"], 14)
        df_15m["atr"] = Indicators.ATR(df_15m, 14)
        df_15m = df_15m.dropna().reset_index(drop=True)
        if len(df_15m) < 2: return None
        curr, prev = df_15m.iloc[-1], df_15m.iloc[-2]
        qty = float(self.positions.get(code, 0.0) or 0.0)
        if qty > 0:
            self.highest_high[code] = max(self.highest_high.get(code, 0.0), float(curr["close"]))
            trail_stop = float(self.highest_high[code] - curr["atr"] * 2.5)
            if float(curr["close"]) < trail_stop or curr["ema10"] < curr["ema20"]:
                return self.create_exit_signal(kline, qty, "Exit")
            return None
        if prev["ema10"] <= prev["ema20"] and curr["ema10"] > curr["ema20"] and float(curr["rsi"]) > 45:
            buy_qty = self._qty()
            if buy_qty <= 0: return None
            return {'strategy_id': self.id, 'code': code, 'dt': kline['dt'], 'direction': 'BUY', 'price': float(kline['close']), 'qty': buy_qty, 'stop_loss': float(curr["close"] - curr["atr"] * 2.0), 'take_profit': None}
        return None

class Strategy18(BaseImplementedStrategy):
    """
    18 - 牛旗形态趋势延续 (Bull Flag Pattern) - 优化版
    根据教学图优化:
    1. 旗杆: 爆发性拉升, 成交量巨量
    2. 旗面: 窄幅下降通道 (Lower Highs/Lows), 价格压缩 (Tightness), 成交量萎缩
    3. 突破: 放量突破旗面上边沿
    4. 目标: 旗杆高度 (Flagpole height)
    """
    def __init__(self):
        super().__init__("18", "18 - 牛旗形态趋势延续", trigger_timeframe="15min")
        self.flagpole_height = {}
        self.flag_top_p = {}

    def on_bar(self, kline):
        df = self.preprocess(kline)
        code = kline["code"]
        if len(df) < 100: return None
        df_15m = Indicators.resample(df, "15min")
        if len(df_15m) < 40: return None
        
        # 形态参数计算
        df_15m["pct_change_10"] = (df_15m["close"] - df_15m["close"].shift(10)) / df_15m["close"].shift(10)
        df_15m["vol_ma_20"] = df_15m["vol"].rolling(20).mean()
        df_15m["tightness"] = Indicators.TIGHTNESS(df_15m["high"], df_15m["low"], 10)
        df_15m["atr"] = Indicators.ATR(df_15m, 14)
        
        curr = df_15m.iloc[-1]
        qty = float(self.positions.get(code, 0.0) or 0.0)
        
        # 止盈止损逻辑
        if qty > 0:
            # 严格按照图示: 旗杆高度目标位
            target = self.entry_price.get(code, 0.0) + self.flagpole_height.get(code, 0.0)
            if float(curr["close"]) >= target:
                return self.create_exit_signal(kline, qty, "Bull Flag Target Reached")
            # 止损放在旗面最低点下方 (ATR缓冲)
            if float(curr["close"]) < self.trailing_stop_level.get(code, 0.0):
                return self.create_exit_signal(kline, qty, "Bull Flag Stop Loss")
            return None
            
        # 1. 检测旗杆 (Flagpole): 爆发拉升 + 放量
        # 要求 10 根 K 线内涨幅超过 1.5 倍的 ATR 总和, 且成交量是均值的 1.5 倍
        recent_atr_sum = df_15m["atr"].iloc[-20:-10].sum()
        
        # --- 靠谱增强: 检查 1小时大趋势 ---
        df_1h = Indicators.resample(df, "1h")
        if len(df_1h) < 20: return None
        ema_1h_20 = Indicators.EMA(df_1h["close"], 20).iloc[-1]
        if float(curr["close"]) < ema_1h_20:
            return None # 1小时级别走势太弱，不打牛旗
        # -----------------------------

        is_pole = (float(curr["close"] - df_15m["close"].shift(10).iloc[-1]) > recent_atr_sum * 1.5) and (float(curr["vol"]) > float(curr["vol_ma_20"]) * 1.5)
        
        # 寻找最近的旗杆作为参考点
        potential_pole = df_15m[(df_15m["pct_change_10"] > 0.035) & (df_15m["vol"] > df_15m["vol_ma_20"] * 1.3)]
        if not potential_pole.empty:
            last_pole = potential_pole.iloc[-1]
            # 修正: 从 df_15m 中查找对应的 shift 值
            idx = last_pole.name
            prev_idx = df_15m.index.get_loc(idx) - 10
            if prev_idx < 0: return None
            pole_height = float(last_pole["close"] - df_15m["close"].iloc[prev_idx])
            
            # 2. 检测旗面 (Flag): 价格在下降通道中压缩
            # 取旗杆后的 15 根 K 线分析
            flag_bars = df_15m.iloc[-12:]
            
            # 特征A: 价格压缩 (Tightness 指标低)
            is_tight = flag_bars["tightness"].min() < 0.025
            
            # 特征B: 高点逐渐下移 (下降通道)
            high_slope = Indicators.SLOPE(flag_bars["high"], 8).iloc[-1]
            is_descending = high_slope < 0
            
            # 特征C: 成交量萎缩
            vol_dry_up = flag_bars["vol"].mean() < last_pole["vol"] * 0.7
            
            # 3. 突破买入: 突破旗面期间的最高点, 且成交量重新放大
            breakout_level = flag_bars["high"].iloc[:-1].max()
            if is_tight and is_descending and vol_dry_up and float(curr["close"]) > breakout_level and float(curr["vol"]) > curr["vol_ma_20"]:
                buy_qty = self._qty()
                if buy_qty <= 0: return None
                
                self.flagpole_height[code] = pole_height
                self.entry_price[code] = float(curr["close"])
                # 止损放在旗面低点
                stop_loss = flag_bars["low"].min() - (curr["atr"] * 0.5)
                self.trailing_stop_level[code] = stop_loss
                
                return {
                    'strategy_id': self.id, 'code': code, 'dt': kline['dt'], 
                    'direction': 'BUY', 'price': float(kline['close']), 'qty': buy_qty, 
                    'stop_loss': stop_loss, 'take_profit': float(curr["close"] + pole_height)
                }
        return None
