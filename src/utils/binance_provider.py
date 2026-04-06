import os
from datetime import datetime, timedelta

import pandas as pd
import requests

from src.utils.config_loader import ConfigLoader
from src.utils.indicators import Indicators


class BinanceProvider:
    """
    Public Binance spot market data provider for crypto backtesting.
    """

    BASE_URL = "https://api.binance.com"
    KLINES_PATH = "/api/v3/klines"
    EXCHANGE_INFO_PATH = "/api/v3/exchangeInfo"
    TICKER_24H_PATH = "/api/v3/ticker/24hr"
    MAX_LIMIT = 1000

    def __init__(self):
        cfg = ConfigLoader.reload()
        self._cache_enabled = bool(cfg.get("data_provider.local_cache_enabled", True))
        cache_dir = str(cfg.get("data_provider.local_cache_dir", "data/history/cache") or "data/history/cache")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(base_dir))
        self._cache_dir = cache_dir if os.path.isabs(cache_dir) else os.path.join(project_root, cache_dir)
        os.makedirs(self._cache_dir, exist_ok=True)
        
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "bailu-zhisuan-crypto/1.0"})
        
        # Load custom API URL or Proxy from config
        custom_url = cfg.get("data_provider.default_api_url", "").strip()
        if custom_url:
            self.BASE_URL = custom_url.rstrip("/")
        
        proxy = cfg.get("data_provider.proxy", "").strip()
        if proxy:
            self.session.proxies = {
                "http": proxy,
                "https": proxy
            }
        elif os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY"):
            # Requests already respects env vars, but we can be explicit if needed
            pass

    def _normalize_symbol(self, code):
        return str(code or "").strip().upper().replace("-", "").replace("/", "")

    def _cache_file_path(self, code, interval):
        safe_code = self._normalize_symbol(code)
        return os.path.join(self._cache_dir, f"binance_{safe_code}_{interval}.csv")

    def _normalize_df(self, code, df):
        if df is None or df.empty:
            return pd.DataFrame()
        work = df.copy()
        required_cols = ["code", "dt", "open", "high", "low", "close", "vol", "amount"]
        for c in required_cols:
            if c not in work.columns:
                return pd.DataFrame()
        work["code"] = str(code or "").upper()
        work["dt"] = pd.to_datetime(work["dt"], errors="coerce", utc=False)
        for c in ["open", "high", "low", "close", "vol", "amount"]:
            work[c] = pd.to_numeric(work[c], errors="coerce")
        work = work.dropna(subset=["dt", "open", "high", "low", "close"])
        work = work.drop_duplicates(subset=["dt"]).sort_values("dt").reset_index(drop=True)
        return work[required_cols]

    def _load_cached_data(self, code, interval, start_time, end_time):
        if not self._cache_enabled:
            return pd.DataFrame(), False
        path = self._cache_file_path(code, interval)
        if not os.path.exists(path):
            return pd.DataFrame(), False
        try:
            df = pd.read_csv(path)
            df = self._normalize_df(code, df)
            if df.empty:
                return pd.DataFrame(), False
            full_coverage = df["dt"].min() <= start_time and df["dt"].max() >= end_time
            return df, bool(full_coverage)
        except Exception:
            return pd.DataFrame(), False

    def _save_cache(self, code, interval, df):
        if not self._cache_enabled or df is None or df.empty:
            return
        path = self._cache_file_path(code, interval)
        try:
            df_save = self._normalize_df(code, df)
            if df_save.empty:
                return
            if os.path.exists(path):
                old_df = pd.read_csv(path)
                old_df = self._normalize_df(code, old_df)
                if not old_df.empty:
                    df_save = pd.concat([old_df, df_save], ignore_index=True)
                    df_save = self._normalize_df(code, df_save)
            df_save.to_csv(path, index=False, encoding="utf-8")
        except Exception:
            return

    def _request_klines(self, symbol, interval, start_ms=None, end_ms=None, limit=1000):
        params = {"symbol": symbol, "interval": interval, "limit": min(int(limit or 1000), self.MAX_LIMIT)}
        if start_ms is not None:
            params["startTime"] = int(start_ms)
        if end_ms is not None:
            params["endTime"] = int(end_ms)
        resp = self.session.get(f"{self.BASE_URL}{self.KLINES_PATH}", params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            return []
        return payload

    def _request_json(self, path, params=None):
        resp = self.session.get(f"{self.BASE_URL}{path}", params=params or {}, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def _interval_to_binance(self, interval):
        mapping = {
            "1min": "1m",
            "5min": "5m",
            "10min": "15m",
            "15min": "15m",
            "30min": "30m",
            "60min": "1h",
            "D": "1d",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
        }
        return mapping.get(str(interval or "1min"), "1m")

    def _fetch_klines(self, code, interval, start_time, end_time):
        symbol = self._normalize_symbol(code)
        binance_interval = self._interval_to_binance(interval)
        cached_df, cache_hit = self._load_cached_data(symbol, interval, start_time, end_time)
        if cache_hit:
            return cached_df[(cached_df["dt"] >= start_time) & (cached_df["dt"] <= end_time)].copy()
        fetch_start = start_time
        if not cached_df.empty:
            cached_min = pd.to_datetime(cached_df["dt"].min())
            cached_max = pd.to_datetime(cached_df["dt"].max())
            if cached_min <= start_time:
                fetch_start = cached_max + timedelta(milliseconds=1)
                if fetch_start > end_time:
                    return cached_df[(cached_df["dt"] >= start_time) & (cached_df["dt"] <= end_time)].copy()
            else:
                fetch_start = start_time
        all_rows = []
        start_ms = int(fetch_start.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        while start_ms < end_ms:
            rows = self._request_klines(symbol, binance_interval, start_ms=start_ms, end_ms=end_ms, limit=self.MAX_LIMIT)
            if not rows:
                break
            for item in rows:
                all_rows.append({
                    "code": symbol,
                    "dt": datetime.utcfromtimestamp(int(item[0]) / 1000),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "vol": float(item[5]),
                    "amount": float(item[7]),
                })
            next_open_time = int(rows[-1][0])
            if next_open_time <= start_ms:
                break
            start_ms = next_open_time + 1
            if len(rows) < self.MAX_LIMIT:
                break
        df = pd.DataFrame(all_rows)
        df = self._normalize_df(symbol, df)
        if not cached_df.empty:
            df = pd.concat([cached_df, df], ignore_index=True)
            df = self._normalize_df(symbol, df)
        self._save_cache(symbol, interval, df)
        if df.empty:
            return df
        return df[(df["dt"] >= start_time) & (df["dt"] <= end_time)].copy()

    def get_latest_bar(self, code):
        symbol = self._normalize_symbol(code)
        try:
            rows = self._request_klines(symbol, "1m", limit=2)
            if not rows:
                return None
            item = rows[-1]
            return {
                "code": symbol,
                "dt": datetime.utcfromtimestamp(int(item[0]) / 1000),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "vol": float(item[5]),
                "amount": float(item[7]),
            }
        except Exception:
            return None

    def get_latest_bars(self, symbols):
        out = {}
        for symbol in symbols or []:
            bar = self.get_latest_bar(symbol)
            if isinstance(bar, dict):
                out[str(symbol).upper()] = bar
        return out

    def list_symbols(self, quote_asset="USDT", limit=60):
        quote = str(quote_asset or "USDT").upper().strip() or "USDT"
        max_items = max(1, min(int(limit or 60), 500))
        try:
            info = self._request_json(self.EXCHANGE_INFO_PATH)
            tickers = self._request_json(self.TICKER_24H_PATH)
            volume_map = {}
            if isinstance(tickers, list):
                for row in tickers:
                    symbol = str(row.get("symbol", "")).upper()
                    try:
                        volume_map[symbol] = float(row.get("quoteVolume", 0) or 0)
                    except Exception:
                        volume_map[symbol] = 0.0
            rows = []
            for row in (info.get("symbols", []) if isinstance(info, dict) else []):
                if str(row.get("status", "")).upper() != "TRADING":
                    continue
                if str(row.get("quoteAsset", "")).upper() != quote:
                    continue
                symbol = str(row.get("symbol", "")).upper()
                if not symbol:
                    continue
                rows.append({
                    "code": symbol,
                    "name": f"{str(row.get('baseAsset', '')).upper()} / {quote}",
                    "pinyin": str(row.get("baseAsset", "")).upper(),
                    "quote_volume": float(volume_map.get(symbol, 0.0)),
                })
            rows.sort(key=lambda x: x.get("quote_volume", 0.0), reverse=True)
            return rows[:max_items]
        except Exception:
            fallback = [
                {"code": "BTCUSDT", "name": "BTC / USDT", "pinyin": "BTC"},
                {"code": "ETHUSDT", "name": "ETH / USDT", "pinyin": "ETH"},
                {"code": "SOLUSDT", "name": "SOL / USDT", "pinyin": "SOL"},
            ]
            return fallback[:max_items]

    def fetch_minute_data(self, code, start_time, end_time):
        return self._fetch_klines(code, "1min", start_time, end_time)

    def fetch_kline_data(self, code, start_time, end_time, interval="1min"):
        tf = str(interval or "1min")
        if tf == "1min":
            return self.fetch_minute_data(code, start_time, end_time)
        if tf in {"5min", "15min", "30min", "60min", "D", "1h", "4h", "1d"}:
            return self._fetch_klines(code, tf, start_time, end_time)
        if tf == "10min":
            df_5m = self._fetch_klines(code, "5min", start_time, end_time)
            return Indicators.resample(df_5m, "10min") if not df_5m.empty else pd.DataFrame()
        df_1m = self.fetch_minute_data(code, start_time, end_time)
        if df_1m.empty:
            return pd.DataFrame()
        return Indicators.resample(df_1m, tf)
