# run_live.py
import asyncio
import os
import json
from datetime import datetime, timedelta
from src.core.live_cabinet import LiveCabinet
from src.utils.config_loader import ConfigLoader
from src.utils.market_scanner import MarketScanner
from src.utils.performance_auditor import PerformanceAuditor

class LiveManager:
    def __init__(self):
        self.config = ConfigLoader.reload()
        self.tasks = {} # symbol -> task
        self.cabinets = {} # symbol -> cabinet
        
        # Load params from config
        self.provider = self._get_provider()
        self.tushare_token = os.environ.get("TUSHARE_TOKEN", "") or self.config.get("data_provider.tushare_token")
        self.initial_capital = self.config.get("system.initial_capital", 1000000.0)
        self.scanner = MarketScanner(provider_type=self.provider)
        self.auditor = PerformanceAuditor()
        
    def _get_provider(self):
        env_provider = os.environ.get("DATA_PROVIDER", "").lower()
        if env_provider: return env_provider
        return self.config.get("data_provider.source", "binance")

    async def start_cabinet(self, symbol):
        if symbol in self.tasks:
            return
        
        print(f"🚀 [Manager] Launching Live Monitor for: {symbol}")
        cabinet = LiveCabinet(
            symbol,
            initial_capital=self.initial_capital,
            provider_type=self.provider,
            tushare_token=self.tushare_token
        )
        self.cabinets[symbol] = cabinet
        task = asyncio.create_task(cabinet.run_live())
        self.tasks[symbol] = task
        
        # Update config to include new target
        self._update_config_targets(symbol)

    def _update_config_targets(self, symbol):
        try:
            with open('config.json', 'r') as f:
                cfg = json.load(f)
            if symbol not in cfg.get("targets", []):
                cfg["targets"].append(symbol)
                with open('config.json', 'w') as f:
                    json.dump(cfg, f, indent=2)
                print(f"📝 [Manager] Added {symbol} to config targets.")
        except Exception as e:
            print(f"⚠️ [Manager] Failed to update config: {e}")

    async def run_scanner_loop(self):
        while True:
            print("🔍 [Manager] Scanning market for new opportunities...")
            try:
                # Get BTC trend first as a safety filter
                btc_data = self.scanner.provider.fetch_kline_data("BTCUSDT", datetime.now() - timedelta(hours=4), datetime.now(), interval="1h")
                if not btc_data.empty:
                    btc_ema = btc_data["close"].rolling(20).mean().iloc[-1]
                    btc_price = btc_data["close"].iloc[-1]
                    
                    if btc_price < btc_ema * 0.99:
                        print("⚠️ [Manager] Market is weak (BTC < EMA20). Skipping aggressive scans for safety.")
                    else:
                        candidates = self.scanner.scan_for_bull_flags(top_n=100)
                        for cand in candidates:
                            symbol = cand['symbol']
                            if symbol not in self.tasks:
                                print(f"✨ [Manager] Found high-quality Bull Flag candidate: {symbol} (Vol Ratio: {cand['vol_dry_ratio']})")
                                await self.start_cabinet(symbol)
                else:
                    print("⚠️ [Manager] Could not get BTC data for regime check. Scanning anyway...")
                    candidates = self.scanner.scan_for_bull_flags(top_n=100)
                    for cand in candidates:
                        symbol = cand['symbol']
                        if symbol not in self.tasks:
                            await self.start_cabinet(symbol)
                            
            except Exception as e:
                print(f"❌ [Manager] Scanner error: {e}")
            
            # Scan every 10 minutes for higher reliability
            await asyncio.sleep(600)

    async def run_audit_loop(self):
        while True:
            # Wait for 24h cycle
            await asyncio.sleep(86400)
            print("📅 [Manager] Time for Daily Performance Audit & Evolution...")
            try:
                res = self.auditor.audit_last_24h()
                if isinstance(res, tuple):
                    report, proposals = res
                    await self.auditor.report_evolution(report, proposals)
                else:
                    print(f"ℹ️ [Manager] Audit Info: {res}")
            except Exception as e:
                print(f"❌ [Manager] Auditor error: {e}")

    async def run(self):
        # 1. Start initial targets
        initial_targets = self.config.get("targets", ["BTCUSDT"])
        print(f"🎯 [Manager] Initial Targets: {', '.join(initial_targets)}")
        
        for symbol in initial_targets:
            await self.start_cabinet(symbol)
            
        # 2. Start Scanner Loop
        scanner_task = asyncio.create_task(self.run_scanner_loop())
        # 3. Start Audit Loop (Daily Evolution)
        audit_task = asyncio.create_task(self.run_audit_loop())
        
        # 4. Wait for all tasks
        while True:
            await asyncio.sleep(60)
            # Check for failed tasks
            dead_symbols = []
            for symbol, task in self.tasks.items():
                if task.done():
                    if task.exception():
                        print(f"💥 [Manager] Cabinet for {symbol} crashed: {task.exception()}")
                    dead_symbols.append(symbol)
            
            for symbol in dead_symbols:
                del self.tasks[symbol]

async def main():
    manager = LiveManager()
    await manager.run()

if __name__ == "__main__":
    asyncio.run(main())
