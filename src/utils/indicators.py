# src/utils/indicators.py
import pandas as pd
import numpy as np

class Indicators:
    """
    Technical Indicators Calculator & Data Resampler
    """
    
    @staticmethod
    def resample(df, rule):
        """
        Resample 1-min data to other timeframes.
        rule: '5min', '15min', '30min', '60min', 'D', 'W'
        """
        # Ensure dt is index
        if 'dt' in df.columns:
            df = df.set_index('dt')
        
        # Resample logic
        agg_dict = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'vol': 'sum',
            'amount': 'sum'
        }
        
        # Handle custom columns if exist
        if 'code' in df.columns:
            agg_dict['code'] = 'first'
            
        resampled = df.resample(rule).agg(agg_dict).dropna()
        
        # Reset index to keep dt as column
        return resampled.reset_index()

    @staticmethod
    def _to_numeric_series(data, preferred_col='close'):
        if isinstance(data, pd.Series):
            return pd.to_numeric(data, errors='coerce')
        if isinstance(data, pd.DataFrame):
            if preferred_col in data.columns:
                return pd.to_numeric(data[preferred_col], errors='coerce')
            for c in ['close', 'high', 'low', 'open', 'volume', 'vol']:
                if c in data.columns:
                    return pd.to_numeric(data[c], errors='coerce')
            numeric_cols = [c for c in data.columns if c not in ('dt', 'code')]
            if numeric_cols:
                return pd.to_numeric(data[numeric_cols[0]], errors='coerce')
            return pd.Series(dtype=float)
        return pd.to_numeric(pd.Series(data), errors='coerce')

    @staticmethod
    def MA(series, window):
        s = Indicators._to_numeric_series(series)
        return s.rolling(window=window).mean()

    @staticmethod
    def EMA(series, window):
        s = Indicators._to_numeric_series(series)
        return s.ewm(span=window, adjust=False).mean()

    @staticmethod
    def MACD(close_series, fast=12, slow=26, signal=9):
        close_series = Indicators._to_numeric_series(close_series)
        exp1 = Indicators.EMA(close_series, fast)
        exp2 = Indicators.EMA(close_series, slow)
        dif = exp1 - exp2
        dea = Indicators.EMA(dif, signal)
        macd = (dif - dea) * 2
        return dif, dea, macd

    @staticmethod
    def RSI(close_series, window=14):
        close_series = Indicators._to_numeric_series(close_series)
        delta = close_series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.fillna(50)
        return rsi
        
    @staticmethod
    def KDJ(high, low, close, n=9, m1=3, m2=3):
        low_min = low.rolling(window=n).min()
        high_max = high.rolling(window=n).max()
        
        rsv = (close - low_min) / (high_max - low_min) * 100
        # Fix division by zero
        rsv = rsv.fillna(50)
        
        k = rsv.ewm(alpha=1/m1, adjust=False).mean()
        d = k.ewm(alpha=1/m2, adjust=False).mean()
        j = 3 * k - 2 * d
        return k, d, j

    @staticmethod
    def ATR(high, low=None, close=None, window=14):
        if low is None and close is None and isinstance(high, pd.DataFrame):
            df = high
            high = Indicators._to_numeric_series(df, 'high')
            low = Indicators._to_numeric_series(df, 'low')
            close = Indicators._to_numeric_series(df, 'close')
        else:
            high = Indicators._to_numeric_series(high, 'high')
            low = Indicators._to_numeric_series(low, 'low')
            close = Indicators._to_numeric_series(close, 'close')
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=window).mean()

    @staticmethod
    def HHV(series, window=14):
        s = Indicators._to_numeric_series(series, 'high')
        return s.rolling(window=window).max()

    @staticmethod
    def LLV(series, window=14):
        s = Indicators._to_numeric_series(series, 'low')
        return s.rolling(window=window).min()

    @staticmethod
    def BollingerBands(close, window=20, num_std=2):
        ma = close.rolling(window=window).mean()
        std = close.rolling(window=window).std()
        upper = ma + (std * num_std)
        lower = ma - (std * num_std)
        return upper, ma, lower

    @staticmethod
    def sma(series, window=14, period=None, **kwargs):
        w = period if period is not None else window
        return Indicators.MA(series, int(w))

    @staticmethod
    def ma(series, window=14, period=None, timeperiod=None, **kwargs):
        w = period if period is not None else (timeperiod if timeperiod is not None else window)
        return Indicators.MA(series, int(w))

    @staticmethod
    def ema(series, window=14, period=None, **kwargs):
        w = period if period is not None else window
        return Indicators.EMA(series, int(w))

    @staticmethod
    def macd(close_series, fast=12, slow=26, signal=9, fastperiod=None, slowperiod=None, signalperiod=None, **kwargs):
        f = fastperiod if fastperiod is not None else fast
        s = slowperiod if slowperiod is not None else slow
        g = signalperiod if signalperiod is not None else signal
        return Indicators.MACD(close_series, fast=int(f), slow=int(s), signal=int(g))

    @staticmethod
    def rsi(close_series, window=14, period=None, timeperiod=None, **kwargs):
        w = period if period is not None else (timeperiod if timeperiod is not None else window)
        return Indicators.RSI(close_series, window=int(w))

    @staticmethod
    def kdj(high, low, close, n=9, m1=3, m2=3):
        return Indicators.KDJ(high, low, close, n=n, m1=m1, m2=m2)

    @staticmethod
    def atr(high, low=None, close=None, window=14, period=None, timeperiod=None, **kwargs):
        w = period if period is not None else (timeperiod if timeperiod is not None else window)
        return Indicators.ATR(high, low, close, window=int(w))

    @staticmethod
    def hhv(series, window=14, period=None, timeperiod=None, **kwargs):
        w = period if period is not None else (timeperiod if timeperiod is not None else window)
        return Indicators.HHV(series, window=int(w))

    @staticmethod
    def llv(series, window=14, period=None, timeperiod=None, **kwargs):
        w = period if period is not None else (timeperiod if timeperiod is not None else window)
        return Indicators.LLV(series, window=int(w))

    @staticmethod
    def bollinger_bands(close, window=20, num_std=2):
        return Indicators.BollingerBands(close, window=window, num_std=num_std)

    @staticmethod
    def CMF(df, window=20):
        """Chaikin Money Flow"""
        mfv = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low'])
        mfv = mfv.replace([np.inf, -np.inf], 0).fillna(0)
        mfv *= df['vol']
        cmf = mfv.rolling(window=window).sum() / df['vol'].rolling(window=window).sum()
        return cmf

    @staticmethod
    def VWAP(df, window=None):
        """VWAP. If window is None, it's cumulative. If window is integer, it's rolling."""
        vpv = df['close'] * df['vol']
        if window is None:
            vwap = vpv.cumsum() / df['vol'].cumsum()
        else:
            vwap = vpv.rolling(window=window).sum() / df['vol'].rolling(window=window).sum()
        return vwap

    @staticmethod
    def OBV(df):
        """On-Balance Volume"""
        obv = (np.sign(df['close'].diff()) * df['vol']).fillna(0).cumsum()
        return obv

    @staticmethod
    def ADX(df, window=14):
        """Average Directional Index"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        plus_dm = high.diff()
        minus_dm = low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        minus_dm = abs(minus_dm)
        
        tr = Indicators.ATR(df, window=1).fillna(0) # TR is ATR(1)
        
        atr = tr.rolling(window=window).mean()
        plus_di = 100 * (plus_dm.rolling(window=window).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=window).mean() / atr)
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        adx = dx.rolling(window=window).mean()
        return adx

    @staticmethod
    def MFI(df, window=14):
        """Money Flow Index"""
        tp = (df['high'] + df['low'] + df['close']) / 3
        rmf = tp * df['vol']
        
        pos_mf = pd.Series(0.0, index=df.index)
        neg_mf = pd.Series(0.0, index=df.index)
        
        diff = tp.diff()
        pos_mf[diff > 0] = rmf[diff > 0]
        neg_mf[diff < 0] = rmf[diff < 0]
        
        mfr = pos_mf.rolling(window=window).sum() / neg_mf.rolling(window=window).sum()
        mfi = 100 - (100 / (1 + mfr))
        return mfi

    @staticmethod
    def SLOPE(series, window=5):
        """Linear regression slope over window bars using numpy."""
        def get_slope(y):
            if len(y) < window or np.all(np.isnan(y)): return 0.0
            x = np.arange(len(y))
            # OLS: slope = cov(x,y) / var(x)
            # Simplification for fixed x = [0, 1, 2, ... n-1]
            n = len(y)
            sum_x = n * (n - 1) / 2
            sum_y = np.sum(y)
            sum_xx = n * (n - 1) * (2 * n - 1) / 6
            sum_xy = np.sum(x * y)
            denominator = (n * sum_xx - sum_x**2)
            if denominator == 0: return 0.0
            slope = (n * sum_xy - sum_x * sum_y) / denominator
            return slope
        return series.rolling(window=window).apply(get_slope, raw=True)

    @staticmethod
    def TIGHTNESS(high, low, window=10):
        """Measures range tightness as (MaxHigh - MinLow) / AveragePrice."""
        max_h = high.rolling(window=window).max()
        min_l = low.rolling(window=window).min()
        avg_p = (high + low) / 2
        return (max_h - min_l) / avg_p.rolling(window=window).mean()
