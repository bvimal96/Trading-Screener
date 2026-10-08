import time
import yfinance as yf
import pandas as pd

class YahooData:
    def __init__(self,tz="Asia/Kolkata"):
        self.tz=tz
        self.dcache={}
        self.icache={}
        self.missing_d={}
        self.missing_i={}

    def clean(self,d):
        if d is None or d.empty:
            return pd.DataFrame()
        x=d.copy()
        if isinstance(x.columns,pd.MultiIndex):
            x.columns=x.columns.get_level_values(0)
        x.index=pd.to_datetime(x.index)
        if x.index.tz is None:
            x.index=x.index.tz_localize("UTC").tz_convert(self.tz)
        else:
            x.index=x.index.tz_convert(self.tz)
        cols=["Open","High","Low","Close","Volume"]
        return x[[c for c in cols if c in x.columns]].dropna(subset=["Close"])

    def _batch(self,symbols,period,interval):
        if not symbols:
            return {}
        out={}
        for start in range(0,len(symbols),50):
            chunk=symbols[start:start+50]
            try:
                raw=yf.download(
                    tickers=chunk,period=period,interval=interval,
                    auto_adjust=False,actions=False,prepost=False,
                    group_by="column",threads=False,progress=False
                )
                if raw is not None and not raw.empty:
                    if isinstance(raw.columns,pd.MultiIndex):
                        level1=list(dict.fromkeys(raw.columns.get_level_values(1)))
                        for sym in chunk:
                            if sym not in level1:
                                continue
                            try:
                                out[sym]=self.clean(raw.xs(sym,axis=1,level=1,drop_level=True))
                            except Exception:
                                pass
                    else:
                        out[chunk[0]]=self.clean(raw)
            except Exception:
                pass
            if start+50<len(symbols):
                time.sleep(1)
        return out

    def prefetch(self,symbols):
        now=time.time()
        dneed=[s for s in symbols if s not in self.dcache or now-self.dcache[s][0]>=900]
        ineed=[s for s in symbols if s not in self.icache or now-self.icache[s][0]>=20]

        for s,d in self._batch(dneed,"60d","1d").items():
            self.dcache[s]=(now,d)
            self.missing_d.pop(s,None)
        for s,d in self._batch(ineed,"1d","5m").items():
            self.icache[s]=(now,d)
            self.missing_i.pop(s,None)

        # Avoid immediate single-symbol retry storms for symbols Yahoo rejects.
        for s in dneed:
            if s not in self.dcache:
                self.missing_d[s]=now
        for s in ineed:
            if s not in self.icache:
                self.missing_i[s]=now

    def daily(self,symbol):
        now=time.time()
        if symbol in self.dcache and now-self.dcache[symbol][0]<900:
            return self.dcache[symbol][1]
        if symbol in self.missing_d and now-self.missing_d[symbol]<60:
            return pd.DataFrame()
        try:
            d=self.clean(yf.Ticker(symbol).history(
                period="60d",interval="1d",auto_adjust=False,
                actions=False,prepost=False
            ))
        except Exception:
            d=pd.DataFrame()
        self.dcache[symbol]=(now,d)
        if d.empty:
            self.missing_d[symbol]=now
        else:
            self.missing_d.pop(symbol,None)
        return d

    def intraday(self,symbol):
        now=time.time()
        if symbol in self.icache and now-self.icache[symbol][0]<20:
            return self.icache[symbol][1]
        if symbol in self.missing_i and now-self.missing_i[symbol]<30:
            return pd.DataFrame()
        try:
            d=self.clean(yf.Ticker(symbol).history(
                period="1d",interval="5m",auto_adjust=False,
                actions=False,prepost=False
            ))
        except Exception:
            d=pd.DataFrame()
        self.icache[symbol]=(now,d)
        if d.empty:
            self.missing_i[symbol]=now
        else:
            self.missing_i.pop(symbol,None)
        return d

    def ltp(self,symbol):
        d=self.intraday(symbol)
        if d.empty:
            d=self.daily(symbol)
        return (float(d.iloc[-1].Close),d.index[-1]) if not d.empty else (None,None)
