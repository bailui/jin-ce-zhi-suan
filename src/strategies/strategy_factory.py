# src/strategies/strategy_factory.py
from src.strategies.implemented_strategies import (
    Strategy00, Strategy10, Strategy11,
    Strategy12, Strategy13, Strategy14, Strategy15, Strategy16, Strategy17, Strategy18
)
from src.strategies.strategy_manager_repo import (
    load_custom_strategies,
    load_disabled_ids,
    load_deleted_ids,
    instantiate_custom_strategy
)
from src.utils.config_loader import ConfigLoader

def create_strategies(apply_active_filter=True):
    """
    Generate the active stock strategies.
    """
    cfg = ConfigLoader.reload()
    asset_class = str(cfg.get("system.asset_class", "equity") or "equity").strip().lower()
    if asset_class == "crypto":
        strategies = [
            Strategy00(),
            Strategy10(),
            Strategy11(),
            Strategy12(),
            Strategy13(),
            Strategy14(),
            Strategy15(),
            Strategy16(),
            Strategy17(),
            Strategy18(),
        ]
    else:
        # Fallback for other asset classes, using basic crypto strategies
        strategies = [
            Strategy00(),
            Strategy10(),
            Strategy11(),
            Strategy12(),
            Strategy13(),
            Strategy14(),
            Strategy15(),
            Strategy16(),
            Strategy17(),
            Strategy18(),
        ]
    builtin_ids = {str(s.id).strip() for s in strategies}
    disabled_ids = load_disabled_ids()
    deleted_ids = load_deleted_ids()
    if deleted_ids:
        strategies = [s for s in strategies if str(s.id) not in deleted_ids]
    custom_rows = load_custom_strategies()
    for row in custom_rows:
        sid = str(row.get("id", "")).strip()
        if sid and sid in builtin_ids:
            continue
        if sid and sid in deleted_ids:
            continue
        if sid and sid in disabled_ids:
            continue
        try:
            strategy = instantiate_custom_strategy(row)
            if strategy is not None:
                strategies.append(strategy)
        except Exception:
            continue
    if disabled_ids:
        strategies = [s for s in strategies if str(s.id) not in disabled_ids]
    if apply_active_filter:
        strategies_before_filter = list(strategies)
        active_ids = cfg.get("strategies.active_ids", [])
        if isinstance(active_ids, list):
            active = {str(x).strip() for x in active_ids if str(x).strip()}
            if active:
                strategies = [s for s in strategies if str(s.id).strip() in active]
                if not strategies:
                    strategies = strategies_before_filter
    return strategies
