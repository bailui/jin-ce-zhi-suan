import pandas as pd
from datetime import datetime, timedelta
from src.utils.data_factory import DataFactory
from src.utils.indicators import Indicators
from src.utils.config_loader import ConfigLoader

class MarketScanner:
    """
    Market Scanner: Scans all liquid crypto pairs for specific patterns (e.g., Bull Flag).
    """
    def __init__(self, provider_type='binance'):
        self.factory = DataFactory(source=provider_type)
        self.provider = self.factory.get_provider()
        self.config = ConfigLoader.reload()
        
    def scan_for_bull_flags(self, top_n=100):
        """
        Scans top N liquid pairs for potential Bull Flag patterns.
        """
        print(f"🔍 Starting Market Scan for Bull Flags (Top {top_n} liquid pairs)...")
        
        # 1. Get top liquid symbols
        symbols_info = self.provider.list_symbols(quote_asset="USDT", limit=top_n)
        symbols = [s['code'] for s in symbols_info]
        
        candidates = []
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24) # Fetch 24h of data to be safe
        
        for symbol in symbols:
            try:
                # Fetch 1h or 15m data for scanning
                df = self.provider.fetch_kline_data(symbol, start_time, end_time, interval="15min")
                if df is None or len(df) < 50:
                    continue
                
                # Lightweight Flagpole Detection
                # Calculate 10-period pct change
                df["pct_change_10"] = (df["close"] - df["close"].shift(10)) / df["close"].shift(10)
                df["vol_ma_20"] = df["vol"].rolling(20).mean()
                
                # Check for a recent pole (within last 20 bars)
                pole_found = False
                pole_idx = -1
                for i in range(1, 21):
                    idx = len(df) - i
                    if idx < 10: break
                    
                    # Pole criteria: Price jump > 8% and Volume > 1.5x average
                    if df["pct_change_10"].iloc[idx] > 0.08 and df["vol"].iloc[idx] > df["vol_ma_20"].iloc[idx] * 1.5:
                        pole_found = True
                        pole_idx = idx
                        break
                
                if not pole_found:
                    continue
                
                # Flag check: Consolidation after the pole
                # Consolidation should be in the bars AFTER the pole
                flag_bars = df.iloc[pole_idx + 1:]
                if len(flag_bars) < 3: # Need at least a few bars of consolidation
                    continue
                
                # Price shouldn't have dropped too much below the pole top
                pole_top = df["close"].iloc[pole_idx]
                flag_low = flag_bars["low"].min()
                if flag_low < pole_top * 0.92: # Dropped more than 8% from top, maybe not a flag
                    continue
                
                # Volume should be drying up
                avg_vol_flag = flag_bars["vol"].mean()
                pole_vol = df["vol"].iloc[pole_idx]
                if avg_vol_flag > pole_vol * 0.7:
                    continue
                
                # If we made it here, it's a candidate
                candidates.append({
                    "symbol": symbol,
                    "pole_time": df["dt"].iloc[pole_idx],
                    "pole_price": pole_top,
                    "curr_price": df["close"].iloc[-1],
                    "pct_from_pole": round((df["close"].iloc[-1] / pole_top - 1) * 100, 2),
                    "vol_dry_ratio": round(avg_vol_flag / pole_vol, 2)
                })
                
            except Exception as e:
                print(f"Error scanning {symbol}: {e}")
                
        # Sort candidates by volume dry ratio (lower is usually better for flags)
        candidates.sort(key=lambda x: x['vol_dry_ratio'])
        return candidates

if __name__ == "__main__":
    scanner = MarketScanner()
    results = scanner.scan_for_bull_flags(top_n=100)
    print("\n🎯 --- Bull Flag Candidates Found ---")
    for res in results:
        print(f"Code: {res['symbol']} | Pole @ {res['pole_price']} | Now: {res['curr_price']} ({res['pct_from_pole']}%) | Vol Ratio: {res['vol_dry_ratio']}")
