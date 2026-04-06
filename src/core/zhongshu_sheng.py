# src/core/zhongshu_sheng.py

from src.utils.runtime_params import get_value
import math

class ZhongshuSheng:
    """
    中书省 (Secretariat): 为每套策略独立生成买卖信号
    """
    def __init__(self, strategies):
        self.strategies = strategies # List of strategy instances

    def generate_signals(self, kline, runnable_strategy_ids=None, strategy_context=None):
        """
        Generate signals for all strategies for the current bar.
        """
        signals = []
        runnable = set(runnable_strategy_ids) if runnable_strategy_ids is not None else None
        ctx = strategy_context if isinstance(strategy_context, dict) else {}
        strategy_ctx_map = {}
        if isinstance(ctx.get("__by_strategy__"), dict):
            strategy_ctx_map = ctx.get("__by_strategy__")
        strategy_kline_map = {}
        if isinstance(ctx.get("__kline_by_strategy__"), dict):
            strategy_kline_map = ctx.get("__kline_by_strategy__")
        for strategy in self.strategies:
            if runnable is not None and strategy.id not in runnable:
                continue
            if hasattr(strategy, "set_backtest_context"):
                scoped_ctx = {}
                if strategy_ctx_map:
                    scoped_ctx = strategy_ctx_map.get(strategy.id, {})
                elif strategy.id in ctx and isinstance(ctx.get(strategy.id), dict):
                    scoped_ctx = ctx.get(strategy.id)
                else:
                    scoped_ctx = ctx
                if isinstance(scoped_ctx, dict) and scoped_ctx:
                    strategy.set_backtest_context(**scoped_ctx)
            kline_for_strategy = strategy_kline_map.get(strategy.id, kline)
            signal = strategy.on_bar(kline_for_strategy)
            if signal:
                if "qty" not in signal or signal.get("qty") is None:
                    signal["qty"] = self._resolve_fallback_qty(strategy)
                qty = float(signal.get("qty", 0) or 0)
                if qty <= 0:
                    continue
                asset_class = str(get_value("system.asset_class", "equity")).strip().lower()
                signal["qty"] = round(qty, 8) if asset_class == "crypto" else int(qty)
                signals.append(signal)
        return signals

    def _resolve_fallback_qty(self, strategy):
        if hasattr(strategy, "_qty"):
            try:
                return float(strategy._qty())
            except Exception:
                pass
        mode = str(get_value("strategy_params.common.order_qty_mode", "fixed")).strip().lower()
        if mode == "cash_pct":
            cash = float(getattr(strategy, "current_cash", 0.0) or 0.0)
            price = float(getattr(strategy, "last_price", 0.0) or 0.0)
            pct = float(get_value("strategy_params.common.order_cash_pct", 0.1))
            if pct > 1:
                pct = pct / 100.0
            pct = max(0.0, min(1.0, pct))
            if cash <= 0 or price <= 0 or pct <= 0:
                return 0
            asset_class = str(get_value("system.asset_class", "equity")).strip().lower()
            if asset_class == "crypto":
                step = float(get_value("trading_rules.qty_step", 0.0001))
                raw_qty = (cash * pct) / price
                return round(math.floor((raw_qty / step) + 1e-9) * step, 8) if step > 0 else round(raw_qty, 8)
            raw_qty = int((cash * pct) // price)
            return int((raw_qty // 100) * 100)
        qty = float(get_value("strategy_params.common.order_qty", 1000))
        asset_class = str(get_value("system.asset_class", "equity")).strip().lower()
        return round(qty, 8) if asset_class == "crypto" else int(qty)

    def update_strategy_state(self, strategy_id, code, position_qty):
        """
        Update strategy state after execution.
        """
        for strategy in self.strategies:
            if strategy.id == strategy_id:
                strategy.update_position(code, position_qty)
                break
