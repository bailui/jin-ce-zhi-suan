import argparse
import asyncio
import copy
import json
import os
import sys
import time
from datetime import datetime, timedelta

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.backtest_cabinet import BacktestCabinet
from src.utils.config_loader import ConfigLoader


OUTPUT_DIR = os.path.join("data", "optimizer")
LATEST_FILE = os.path.join(OUTPUT_DIR, "crypto_optimizer_latest.json")


def deep_set(payload, path, value):
    cur = payload
    parts = str(path).split(".")
    for key in parts[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[parts[-1]] = value


class ConfigOverride:
    def __init__(self, new_config):
        self.new_config = new_config
        self.loader = ConfigLoader.reload()
        self.original_reload = ConfigLoader.reload

    def __enter__(self):
        self.loader._config = self.new_config

        @classmethod
        def _patched_reload(cls, config_path="config.json"):
            return self.loader

        ConfigLoader.reload = _patched_reload
        return self.loader

    def __exit__(self, exc_type, exc, tb):
        ConfigLoader.reload = self.original_reload


async def run_single_case(symbol, strategy_id, start_date, end_date, capital, params):
    events = {"result": None}

    async def callback(event_type, data):
        if event_type == "backtest_result":
            events["result"] = data

    base_cfg = ConfigLoader.reload().to_dict()
    cfg = copy.deepcopy(base_cfg)
    cfg.setdefault("strategies", {})["active_ids"] = [str(strategy_id)]
    for key, value in params.items():
        deep_set(cfg, f"strategy_params.{strategy_id}.{key}", value)

    with ConfigOverride(cfg):
        cab = BacktestCabinet(
            stock_code=symbol,
            strategy_id=str(strategy_id),
            initial_capital=float(capital),
            event_callback=callback,
        )
        await cab.run(start_date=start_date, end_date=end_date)

    result = events["result"] or {}
    ranking = result.get("ranking", []) if isinstance(result, dict) else []
    row = ranking[0] if ranking else {}
    annual = float(row.get("annualized_roi", 0.0) or 0.0)
    win_rate = float(row.get("win_rate", 0.0) or 0.0)
    max_dd = abs(float(row.get("max_dd", 0.0) or 0.0))
    trades = int(row.get("total_trades", 0) or 0)
    score = annual * 100 + win_rate * 35 - max_dd * 80 - (0 if trades >= 4 else 12)
    return {
        "symbol": symbol,
        "strategy_id": str(strategy_id),
        "params": params,
        "score": round(score, 4),
        "annualized_roi": annual,
        "win_rate": win_rate,
        "max_dd": -max_dd,
        "total_trades": trades,
        "rating": row.get("rating", ""),
    }


async def optimize(symbols, days, capital):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=int(days))
    grids = {
        "11": [
            {"breakout_lookback": b, "atr_stop_mult": a}
            for b in [18, 20, 24]
            for a in [2.0, 2.2, 2.6]
        ],
        "12": [
            {"atr_band_mult": a, "entry_rsi_min": r1, "exit_rsi_min": r2}
            for a in [2.4, 2.8, 3.2]
            for r1 in [52, 54, 56]
            for r2 in [42, 46]
        ],
    }
    results = []
    for strategy_id, cases in grids.items():
        for params in cases:
            case_rows = []
            for symbol in symbols:
                row = await run_single_case(symbol, strategy_id, start_date, end_date, capital, params)
                case_rows.append(row)
            avg_score = sum(x["score"] for x in case_rows) / len(case_rows)
            avg_win = sum(float(x["win_rate"]) for x in case_rows) / len(case_rows)
            avg_roi = sum(float(x["annualized_roi"]) for x in case_rows) / len(case_rows)
            avg_dd = sum(float(x["max_dd"]) for x in case_rows) / len(case_rows)
            results.append({
                "strategy_id": strategy_id,
                "params": params,
                "score": round(avg_score, 4),
                "avg_win_rate": round(avg_win, 4),
                "avg_annualized_roi": round(avg_roi, 4),
                "avg_max_dd": round(avg_dd, 4),
                "avg_trades": round(sum(int(x["total_trades"]) for x in case_rows) / len(case_rows), 2),
                "symbols": case_rows,
            })
    results.sort(key=lambda x: (float(x.get("avg_trades", 0.0)), float(x.get("score", 0.0))), reverse=True)
    summary = {
        "status": "success",
        "generated_at": datetime.utcnow().isoformat(),
        "days": int(days),
        "capital": float(capital),
        "symbols": symbols,
        "top_results": results[:10],
        "best_by_strategy": {
            sid: next((x for x in results if x.get("strategy_id") == sid), None)
            for sid in ["11", "12"]
        },
    }
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(LATEST_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    return summary


async def main():
    parser = argparse.ArgumentParser(description="Crypto strategy parameter optimizer")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--capital", type=float, default=200000)
    args = parser.parse_args()
    symbols = [str(x).strip().upper() for x in str(args.symbols).split(",") if str(x).strip()]
    result = await optimize(symbols=symbols, days=args.days, capital=args.capital)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
