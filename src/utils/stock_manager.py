from datetime import datetime, timedelta

from src.utils.binance_provider import BinanceProvider


class SymbolManager:
    def __init__(self):
        self.symbols = [
            {"code": "BTCUSDT", "name": "Bitcoin / Tether", "pinyin": "BTC"},
            {"code": "ETHUSDT", "name": "Ethereum / Tether", "pinyin": "ETH"},
            {"code": "SOLUSDT", "name": "Solana / Tether", "pinyin": "SOL"},
            {"code": "BNBUSDT", "name": "BNB / Tether", "pinyin": "BNB"},
            {"code": "XRPUSDT", "name": "XRP / Tether", "pinyin": "XRP"},
            {"code": "DOGEUSDT", "name": "Dogecoin / Tether", "pinyin": "DOGE"},
            {"code": "ADAUSDT", "name": "Cardano / Tether", "pinyin": "ADA"},
            {"code": "AVAXUSDT", "name": "Avalanche / Tether", "pinyin": "AVAX"},
            {"code": "LINKUSDT", "name": "Chainlink / Tether", "pinyin": "LINK"},
            {"code": "SUIUSDT", "name": "Sui / Tether", "pinyin": "SUI"},
        ]
        self._provider = BinanceProvider()
        self._last_refresh_at = None

    def _refresh_dynamic_symbols(self):
        now = datetime.utcnow()
        if self._last_refresh_at and (now - self._last_refresh_at) < timedelta(minutes=15):
            return
        try:
            dynamic_rows = self._provider.list_symbols(limit=120)
        except Exception:
            dynamic_rows = []
        if dynamic_rows:
            merged = {}
            for row in self.symbols + dynamic_rows:
                code = str(row.get("code", "")).upper().strip()
                if not code:
                    continue
                merged[code] = {
                    "code": code,
                    "name": str(row.get("name", code)),
                    "pinyin": str(row.get("pinyin", code.replace("USDT", ""))).upper(),
                }
            self.symbols = list(merged.values())
            self._last_refresh_at = now

    def search(self, query):
        if not query:
            return []
        self._refresh_dynamic_symbols()

        query = str(query).upper().replace("/", "").replace("-", "").replace("_", "").strip()
        results = []

        for symbol in self.symbols:
            code = str(symbol.get('code', '')).upper()
            name = str(symbol.get('name', '')).upper()
            pinyin = str(symbol.get('pinyin', '')).upper()
            if query in code or query in name or (pinyin and query in pinyin):
                results.append(symbol)
                if len(results) >= 10:
                    break

        return results

symbol_manager = SymbolManager()
