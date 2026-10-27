import os
import time
import pandas as pd
from .alerts import notify

def _closed_bars(frame):
    if frame is None or frame.empty:
        return frame
    x=frame.copy().sort_index()
    now=pd.Timestamp.now(tz="Asia/Kolkata")
    keep=[]
    for ts in x.index:
        local=ts.tz_convert("Asia/Kolkata") if ts.tzinfo else ts.tz_localize("Asia/Kolkata")
        minute=local.hour*60+local.minute
        complete=local+pd.Timedelta(minutes=60)<=now
        in_session=9*60+15<=minute<15*60+15
        aligned=(minute-(9*60+15))%60==0
        keep.append(bool(complete and in_session and aligned))
    return x.loc[keep]

def _supertrend(frame,factor=3.0,period=10):
    x=frame.copy()
    prev=x["Close"].shift(1)
    tr=pd.concat([x["High"]-x["Low"],(x["High"]-prev).abs(),(x["Low"]-prev).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/period,min_periods=period,adjust=False).mean()
    mid=(x["High"]+x["Low"])/2
    up=mid-factor*atr
    dn=mid+factor*atr
    trend_up=pd.Series(index=x.index,dtype=float)
    trend_dn=pd.Series(index=x.index,dtype=float)
    trend=pd.Series(index=x.index,dtype=int)
    for i in range(len(x)):
        if i==0 or pd.isna(atr.iloc[i]):
            trend_up.iloc[i]=up.iloc[i]
            trend_dn.iloc[i]=dn.iloc[i]
            trend.iloc[i]=1
            continue
        pu=trend_up.iloc[i-1]
        pdn=trend_dn.iloc[i-1]
        trend_up.iloc[i]=max(up.iloc[i],pu) if x["Close"].iloc[i-1]>pu else up.iloc[i]
        trend_dn.iloc[i]=min(dn.iloc[i],pdn) if x["Close"].iloc[i-1]<pdn else dn.iloc[i]
        trend.iloc[i]=1 if x["Close"].iloc[i]>pdn else (-1 if x["Close"].iloc[i]<pu else trend.iloc[i-1])
    line=pd.Series(index=x.index,dtype=float)
    line.loc[trend==1]=trend_up.loc[trend==1]
    line.loc[trend==-1]=trend_dn.loc[trend==-1]
    return line

def scan_hourly(app,universe,state):
    data=app.state.data
    state["error"]=None
    symbols=[item["yahoo"] for item in universe]
    try:
        data.prefetch_hourly(symbols)
    except Exception as exc:
        state["error"]=str(exc)
    rows=[]
    now=time.time()
    for item in universe:
        try:
            raw=data.hourly(item["yahoo"])
            bars=_closed_bars(raw)
            if bars is None or len(bars)<60:
                continue
            st=_supertrend(bars,3.0,10)
            ema=bars["Close"].ewm(span=50,adjust=False,min_periods=50).mean()
            bar=bars.iloc[-1]
            stv=float(st.iloc[-1]); emav=float(ema.iloc[-1])
            if pd.isna(stv) or pd.isna(emav):
                continue
            o,h,l,c=[float(bar[k]) for k in ("Open","High","Low","Close")]
            above=min(o,h,l,c)>stv and min(o,h,l,c)>emav
            below=max(o,h,l,c)<stv and max(o,h,l,c)<emav
            if not above and not below:
                continue
            side="BUY" if above else "SELL"
            bt=bars.index[-1]
            bt=bt.tz_localize("Asia/Kolkata") if bt.tzinfo is None else bt.tz_convert("Asia/Kolkata")
            sid=f"hourly:{item['symbol']}:{bt.isoformat()}:{side}"
            signal={"symbol":item["symbol"],"name":item["name"],"strategy":"Hourly Supertrend + EMA 50","side":side,
                "signal_time":bt.isoformat(),"entry":round(c,2),"ltp":round(c,2),"supertrend":round(stv,2),
                "ema":round(emav,2),"signal_id":sid,"updated":now,
                "reference":"Completed 1-hour candle; full OHLC above/below both lines"}
            rows.append(signal)
            if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
                notify(signal,os.getenv("PUBLIC_URL",""))
        except Exception:
            continue
    priority={"NIFTY":0,"BANKNIFTY":1}
    rows.sort(key=lambda item:(priority.get(item["symbol"],2),item["symbol"]))
    state["rows"]=rows
    state["updated"]=now
