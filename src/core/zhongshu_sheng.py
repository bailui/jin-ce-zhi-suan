# src/core/zhongshu_sheng.py

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
        runnable = set(runnable_strategy_ids) if runnable_strategy_ids else None
        ctx = strategy_context if isinstance(strategy_context, dict) else {}
        for strategy in self.strategies:
            if runnable is not None and strategy.id not in runnable:
                continue
            if ctx and hasattr(strategy, "set_backtest_context"):
                strategy.set_backtest_context(**ctx)
            signal = strategy.on_bar(kline)
            if signal:
                qty = int(signal.get("qty", 0))
                if qty <= 0:
                    continue
                signals.append(signal)
        return signals

    def update_strategy_state(self, strategy_id, code, position_qty):
        """
        Update strategy state after execution.
        """
        for strategy in self.strategies:
            if strategy.id == strategy_id:
                strategy.update_position(code, position_qty)
                break
