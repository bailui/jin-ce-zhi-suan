# src/utils/tushare_provider.py
import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import os
from src.utils.config_loader import ConfigLoader
from src.utils.indicators import Indicators

class TushareProvider:
    """
    Tushare Pro Data Provider
    """
    def __init__(self, token=None):
        # Default to a placeholder token if none provided. User must replace this.
        self.token = token
        cfg = ConfigLoader.reload()
        self._cache_enabled = bool(cfg.get("data_provider.local_cache_enabled", True))
        cache_dir = str(cfg.get("data_provider.local_cache_dir", "data/history/cache") or "data/history/cache")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(base_dir))
        self._cache_dir = cache_dir if os.path.isabs(cache_dir) else os.path.join(project_root, cache_dir)
        os.makedirs(self._cache_dir, exist_ok=True)
        import tushare.pro.client as client
        client.DataApi._DataApi__http_url = "http://tushare.xyz"
        if self.token:
            ts.set_token(self.token)
            self.pro = ts.pro_api()
        else:
            self.pro = None
            print("⚠️ Warning: Tushare Token not provided. Please initialize with a valid token.")

    def _cache_file_path(self, code, interval="1min"):
        safe_code = str(code).upper().replace(".", "_")
        return os.path.join(self._cache_dir, f"tushare_{safe_code}_{interval}.csv")

    def _normalize_minutes_df(self, df):
        if df is None or df.empty:
            return pd.DataFrame()
        work = df.copy()
        if "trade_time" in work.columns and "dt" not in work.columns:
            work = work.rename(columns={"trade_time": "dt"})
        if "ts_code" in work.columns and "code" not in work.columns:
            work = work.rename(columns={"ts_code": "code"})
        required_cols = ["code", "open", "high", "low", "close", "vol", "amount", "dt"]
        for c in required_cols:
            if c not in work.columns:
                return pd.DataFrame()
        work["dt"] = pd.to_datetime(work["dt"])
        for c in ["open", "high", "low", "close", "vol", "amount"]:
            work[c] = pd.to_numeric(work[c], errors="coerce")
        work = work.dropna(subset=["dt", "open", "high", "low", "close"])
        work = work.drop_duplicates(subset=["dt"]).sort_values("dt").reset_index(drop=True)
        return work[["code", "dt", "open", "high", "low", "close", "vol", "amount"]]

    def _load_cached_minute_data(self, code, start_time, end_time):
        if not self._cache_enabled:
            return pd.DataFrame(), False
        path = self._cache_file_path(code, "1min")
        if not os.path.exists(path):
            return pd.DataFrame(), False
        try:
            df = pd.read_csv(path)
            if "dt" in df.columns:
                df["dt"] = pd.to_datetime(df["dt"])
            df = self._normalize_minutes_df(df)
            if df.empty:
                return pd.DataFrame(), False
            full_coverage = df["dt"].min() <= start_time and df["dt"].max() >= end_time
            df_range = df[(df["dt"] >= start_time) & (df["dt"] <= end_time)].copy()
            return df_range, bool(full_coverage and not df_range.empty)
        except Exception:
            return pd.DataFrame(), False

    def _save_minute_cache(self, code, df):
        if not self._cache_enabled or df is None or df.empty:
            return
        path = self._cache_file_path(code, "1min")
        try:
            df_save = self._normalize_minutes_df(df)
            if df_save.empty:
                return
            if os.path.exists(path):
                old_df = pd.read_csv(path)
                if "dt" in old_df.columns:
                    old_df["dt"] = pd.to_datetime(old_df["dt"])
                old_df = self._normalize_minutes_df(old_df)
                if not old_df.empty:
                    df_save = pd.concat([old_df, df_save], ignore_index=True)
                    df_save = self._normalize_minutes_df(df_save)
            df_save.to_csv(path, index=False, encoding="utf-8")
        except Exception:
            return

    def set_token(self, token):
        self.token = token
        import tushare.pro.client as client
        client.DataApi._DataApi__http_url = "http://tushare.xyz"
        ts.set_token(self.token)
        self.pro = ts.pro_api()

    def get_latest_bar(self, code):
        """
        Get the latest real-time quote for a stock.
        Returns a dict in the standard format.
        """
        try:
            # Optimized: Use Tushare Pro 'rt_min' if available (requires permissions)
            # This is cleaner than scraping.
            # Example: pro.rt_min(ts_code='600000.SH')
            
            # Normalize code (rt_min expects ts_code like 600000.SH)
            
            # Try rt_min first (Official Real-time Minute API)
            try:
                df = self.pro.rt_min(ts_code=code)
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    # Format: ts_code, freq, time, open, close, high, low, vol, amount
                    # Time is just HH:MM:SS, we need date.
                    today = datetime.now().strftime("%Y-%m-%d")
                    dt_str = f"{today} {row['time']}"
                    dt = pd.to_datetime(dt_str)
                    
                    return {
                        'code': row['ts_code'],
                        'dt': dt,
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'vol': float(row['vol']),
                        'amount': float(row['amount'])
                    }
            except Exception as e_rt:
                # print(f"DEBUG: rt_min failed ({e_rt}), falling back to get_realtime_quotes")
                pass

            # Fallback to get_realtime_quotes (Scraping)
            df = ts.get_realtime_quotes(code)
            if df is None or df.empty:
                # Fallback to pro.daily for latest close (not real-time but better than nothing)
                end_date = datetime.now().strftime("%Y%m%d")
                start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
                df_daily = self.pro.daily(ts_code=code, start_date=start_date, end_date=end_date)
                
                if df_daily is not None and not df_daily.empty:
                    row = df_daily.iloc[0] # Latest
                    return {
                        'code': code,
                        'dt': pd.to_datetime(row['trade_date']),
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'vol': float(row['vol']) * 100, # Hand is unit? No, usually vol is lot or share. Tushare daily vol is "hand" (100 shares)? No, it says "Vol (Hand)". Let's assume hand.
                        'amount': float(row['amount']) * 1000 # Amount is usually in thousands?
                    }
                return None
                
            row = df.iloc[0]
            
            # Normalize format
            # Tushare RT columns: name, open, pre_close, price, high, low, bid, ask, volume, amount, date, time
            
            # Combine date and time
            # Note: get_realtime_quotes returns different columns based on source
            # For tushare < 1.3, it uses sina.
            
            date_str = str(row['date'])
            time_str = str(row['time'])
            dt_str = f"{date_str} {time_str}"
            dt = pd.to_datetime(dt_str)
            
            return {
                'code': code,
                'dt': dt,
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['price']), # Current price
                'vol': float(row['volume']), # Check unit: usually shares?
                'amount': float(row['amount']) # Check unit: usually Yuan?
            }
        except Exception as e:
            # print(f"Error fetching Tushare RT data: {e}")
            # Try fallback inside exception if get_realtime_quotes crashed (e.g. network issue or parsing issue)
            try:
                 end_date = datetime.now().strftime("%Y%m%d")
                 start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
                 df_daily = self.pro.daily(ts_code=code, start_date=start_date, end_date=end_date)
                 if df_daily is not None and not df_daily.empty:
                    row = df_daily.iloc[0]
                    return {
                        'code': code,
                        'dt': pd.to_datetime(row['trade_date']),
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'vol': float(row['vol']) * 100,
                        'amount': float(row['amount']) * 1000
                    }
            except:
                pass
            return None

    def fetch_minute_data(self, code, start_time, end_time):
        """
        Fetch historical minute data via Tushare Pro (requires points/permission).
        Interface: pro.stk_mins or standard ts.pro_bar
        """
        if not self.pro:
            return pd.DataFrame()
        cached_df, cache_hit = self._load_cached_minute_data(code, start_time, end_time)
        if cache_hit:
            return cached_df
        fetch_start = start_time
        if not cached_df.empty:
            fetch_start = cached_df["dt"].max() + timedelta(minutes=1)
            if fetch_start > end_time:
                return cached_df
            
        # Format dates: YYYY-MM-DD HH:MM:SS
        start_str = fetch_start.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            print(f"DEBUG: Requesting Tushare data for {code} ({start_str} - {end_str})")
            
            # Use pro.stk_mins as it proved more reliable for the user's specific token/permission
            df = self.pro.stk_mins(ts_code=code, freq='1min', start_date=start_str, end_date=end_str)
            
            if df is None or df.empty:
                print(f"⚠️ Tushare stk_mins returned empty for {code}.")
                return cached_df if not cached_df.empty else pd.DataFrame()
                
            # Columns: ts_code, trade_time, open, close, high, low, vol, amount
            # Rename
            df = self._normalize_minutes_df(df)
            if not cached_df.empty:
                df = pd.concat([cached_df, df], ignore_index=True)
                df = self._normalize_minutes_df(df)
            self._save_minute_cache(code, df)
            return df
            
        except Exception as e:
            print(f"Error fetching Tushare history: {e}")
            return cached_df if not cached_df.empty else pd.DataFrame()

    def _fetch_stk_mins(self, code, start_time, end_time, freq="1min"):
        if not self.pro:
            return pd.DataFrame()
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            df = self.pro.stk_mins(
                ts_code=code,
                freq=str(freq),
                start_date=start_str,
                end_date=end_str
            )
            return self._normalize_minutes_df(df)
        except Exception:
            return pd.DataFrame()

    def fetch_kline_data(self, code, start_time, end_time, interval="1min"):
        tf = str(interval or "1min")
        if tf == "1min":
            return self.fetch_minute_data(code, start_time, end_time)
        if tf == "D":
            df_d = self.fetch_daily_data(code, start_time, end_time)
            if not df_d.empty:
                return df_d
            df_1m = self.fetch_minute_data(code, start_time, end_time)
            return Indicators.resample(df_1m, "D") if not df_1m.empty else pd.DataFrame()
        freq_map = {
            "5min": "5min",
            "10min": "10min",
            "15min": "15min",
            "30min": "30min",
            "60min": "60min"
        }
        if tf in freq_map:
            df_tf = self._fetch_stk_mins(code, start_time, end_time, freq=freq_map[tf])
            if not df_tf.empty:
                return df_tf
        df_1m = self.fetch_minute_data(code, start_time, end_time)
        if df_1m.empty:
            return pd.DataFrame()
        return Indicators.resample(df_1m, tf)

    def fetch_daily_data(self, code, start_time, end_time):
        if not self.pro:
            return pd.DataFrame()
        start_str = start_time.strftime("%Y%m%d")
        end_str = end_time.strftime("%Y%m%d")
        try:
            df = self.pro.daily(ts_code=code, start_date=start_str, end_date=end_str)
            if df is None or df.empty:
                return pd.DataFrame()
            work = df.copy()
            if "trade_date" not in work.columns:
                return pd.DataFrame()
            work["dt"] = pd.to_datetime(work["trade_date"], format="%Y%m%d", errors="coerce")
            work["open"] = pd.to_numeric(work.get("open"), errors="coerce")
            work["high"] = pd.to_numeric(work.get("high"), errors="coerce")
            work["low"] = pd.to_numeric(work.get("low"), errors="coerce")
            work["close"] = pd.to_numeric(work.get("close"), errors="coerce")
            work["vol"] = pd.to_numeric(work.get("vol"), errors="coerce") * 100.0
            work["amount"] = pd.to_numeric(work.get("amount"), errors="coerce") * 1000.0
            work["code"] = code
            work = work.dropna(subset=["dt", "open", "high", "low", "close"])
            work = work.sort_values("dt").drop_duplicates(subset=["dt"]).reset_index(drop=True)
            return work[["code", "dt", "open", "high", "low", "close", "vol", "amount"]]
        except Exception:
            return pd.DataFrame()
