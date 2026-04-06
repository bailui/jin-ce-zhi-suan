# cron_live.py
import asyncio
import os
import json
from datetime import datetime, timedelta
from src.core.live_cabinet import LiveCabinet
from src.utils.config_loader import ConfigLoader
from src.utils.market_scanner import MarketScanner
from src.utils.performance_auditor import PerformanceAuditor

async def run_once():
    print(f"🕒 [Cron] Starting One-Shot Live Audit at {datetime.now()}")
    config = ConfigLoader.reload()
    
    # 1. Setup Environment
    provider = os.environ.get("DATA_PROVIDER") or config.get("data_provider.source", "binance")
    initial_capital = config.get("system.initial_capital", 1000000.0)
    targets = config.get("targets", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    
    scanner = MarketScanner(provider_type=provider)
    
    # 2. Market Regime Check (BTC Filter)
    try:
        btc_data = scanner.provider.fetch_kline_data("BTCUSDT", datetime.now() - timedelta(hours=4), datetime.now(), interval="1h")
        if not btc_data.empty:
            btc_ema = btc_data["close"].rolling(20).mean().iloc[-1]
            btc_price = btc_data["close"].iloc[-1]
            if btc_price < btc_ema * 0.99:
                print("⚠️ [Cron] Market is weak. Skipping aggressive scans.")
            else:
                # Scan for new opportunities
                candidates = scanner.scan_for_bull_flags(top_n=50)
                for cand in candidates:
                    symbol = cand['symbol']
                    if symbol not in targets:
                        print(f"✨ [Cron] Found new Bull Flag: {symbol}. Adding to targets.")
                        targets.append(symbol)
                        # Update config.json persistence
                        config.set("targets", targets)
    except Exception as e:
        print(f"❌ [Cron] Regime check failed: {e}")

    # 3. Execute Strategies for all targets
    for symbol in targets:
        print(f"🛰️ [Cron] Auditing {symbol}...")
        try:
            cabinet = LiveCabinet(
                symbol,
                initial_capital=initial_capital,
                provider_type=provider
            )
            # Custom one-shot run: Warm up + 1 tick check
            await cabinet.warm_up()
            # In one-shot mode, we just check the latest signal once
            # The cabinet.run_live() is a loop, so we manually call the tick logic
            await cabinet.refresh_data()
            await cabinet.execute_strategies()
            print(f"✅ [Cron] {symbol} audit complete.")
        except Exception as e:
            print(f"💥 [Cron] Error auditing {symbol}: {e}")

    # 4. Daily Evolution (if it's a new day or forced)
    # For now, just run it every time in Cron mode to ensure visibility
    try:
        auditor = PerformanceAuditor()
        res = auditor.audit_last_24h()
        if isinstance(res, tuple):
            report, proposals = res
            await auditor.report_evolution(report, proposals)
    except:
        pass

if __name__ == "__main__":
    asyncio.run(run_once())
