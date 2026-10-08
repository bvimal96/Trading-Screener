import time
import yfinance as yf
import pandas as pd

class YahooData:
    def __init__(self,tz="Asia/Kolkata"):
        self.tz=tz
        self.dcache={}
        self.icache={}

    def clean(self,d):
        if d is None or d.empty:
            return pd.DataFrame()
        if isinstance(d.columns,pd.MultiIndex):
            d.columns=d.columns.get_level_values(-1)
        d.index=pd.to_datetime(d.index)
        if d.index.tz is None:
            d.index=d.index.tz_localize("UTC").tz_convert(self.tz)
        else:
            d.index=d.index.tz_convert(self.tz)
        cols=["Open","High","Low","Close","Volume"]
        return d[[c for c in cols if c in d.columns]].dropna(subset=["Close"])

    def daily(self,symbol):
        if symbol in self.dcache and time.time()-self.dcache[symbol][0]<900:
            return self.dcache[symbol][1]
        try:
            d=self.clean(yf.Ticker(symbol).history(
                period="60d",interval="1d",auto_adjust=False,
                actions=False,prepost=False
            ))
        except Exception:
            d=pd.DataFrame()
        self.dcache[symbol]=(time.time(),d)
        return d

    def intraday(self,symbol):
        # Only today's 5-minute bars are required for breakout detection.
        if symbol in self.icache and time.time()-self.icache[symbol][0]<20:
            return self.icache[symbol][1]
        try:
            d=self.clean(yf.Ticker(symbol).history(
                period="1d",interval="5m",auto_adjust=False,
                actions=False,prepost=False
            ))
        except Exception:
            d=pd.DataFrame()
        self.icache[symbol]=(time.time(),d)
        return d

    def ltp(self,symbol):
        d=self.intraday(symbol)
        if d.empty:
            d=self.daily(symbol)
        return (float(d.iloc[-1].Close),d.index[-1]) if not d.empty else (None,None)
