import pandas as pd

def days(d):
    x=d.copy()
    x["D"]=x.index.date
    return x.groupby("D").agg(
        Open=("Open","first"),
        High=("High","max"),
        Low=("Low","min"),
        Close=("Close","last")
    )

def period_index(idx, freq):
    if getattr(idx, "tz", None) is not None:
        idx=idx.tz_localize(None)
    return idx.to_period(freq)

def session_intraday(i):
    if i is None or i.empty:
        return i
    x=i.copy()
    x["D"]=x.index.date
    return x[x["D"]==x["D"].iloc[-1]].sort_index()

def breakout_time(i, level, side):
    x=session_intraday(i)
    if x is None or x.empty:
        return None
    if side=="BUY":
        normal=(x["High"].shift(1)<=level) & (x["High"]>level)
        gap=(x["Open"]>level) & (x.index==x.index[0])
    else:
        normal=(x["Low"].shift(1)>=level) & (x["Low"]<level)
        gap=(x["Open"]<level) & (x.index==x.index[0])
    hits=x.index[normal | gap]
    return hits[0] if len(hits) else None

def exit_touch(i, entry_time, sl, target, side):
    """Return the first SL/target touch after entry. If both occur in one bar,
    use SL-first (conservative) because OHLC cannot reveal the intrabar order."""
    x=session_intraday(i)
    if x is None or x.empty or entry_time is None:
        return "OPEN", None
    x=x[x.index>=entry_time]
    for ts,row in x.iterrows():
        if side=="BUY":
            sl_hit=float(row["Low"])<=sl
            target_hit=float(row["High"])>=target
        else:
            sl_hit=float(row["High"])>=sl
            target_hit=float(row["Low"])<=target
        if sl_hit and target_hit:
            return "SL HIT", ts
        if sl_hit:
            return "SL HIT", ts
        if target_hit:
            return "TARGET HIT", ts
    return "OPEN", None

def sig(strategy,symbol,name,side,e,rg,rr,ltp,ref,i):
    sl=e-rg if side=="BUY" else e+rg
    target=e+rr*rg if side=="BUY" else e-rr*rg
    entry_time=breakout_time(i,e,side)
    status,event_time=exit_touch(i,entry_time,sl,target,side)
    return {
        "strategy":strategy,
        "symbol":symbol,
        "name":name,
        "side":side,
        "entry":round(e,2),
        "ltp":round(ltp,2),
        "sl":round(sl,2),
        "target":round(target,2),
        "range":round(rg,2),
        "reference":ref,
        "status":status,
        "entry_time":entry_time.isoformat() if entry_time is not None else None,
        "event_time":event_time.isoformat() if event_time is not None else None
    }

def rolling(symbol,name,d,i,ltp,rr):
    x=days(d)
    if i is not None and not i.empty:
        today=i.index[-1].date()
        x=x[x.index < today]
    if len(x)<2:
        return
    r=x.iloc[-2:]
    hi,lo=float(r.High.max()),float(r.Low.min())
    rg=hi-lo
    if breakout_time(i,hi,"BUY") is not None:
        return sig("Rolling 2-Day",symbol,name,"BUY",hi,rg,rr,ltp,"Previous 2 completed days",i)
    if breakout_time(i,lo,"SELL") is not None:
        return sig("Rolling 2-Day",symbol,name,"SELL",lo,rg,rr,ltp,"Previous 2 completed days",i)

def weekly(symbol,name,d,i,ltp,off,rr):
    x=d.copy()
    x["W"]=period_index(x.index,"W-FRI")
    g=x.groupby("W").agg(High=("High","max"),Low=("Low","min"))
    if len(g)<2:
        return
    cur=period_index(pd.DatetimeIndex([d.index[-1]]),"W-FRI")[0]
    p=g[g.index < cur]
    if p.empty:
        return
    p=p.iloc[-1]
    buy=float(p.High)*(1+off)
    sell=float(p.Low)*(1-off)
    rg=buy-sell
    if breakout_time(i,buy,"BUY") is not None:
        return sig("Weekly High/Low",symbol,name,"BUY",buy,rg,rr,ltp,"Previous completed week",i)
    if breakout_time(i,sell,"SELL") is not None:
        return sig("Weekly High/Low",symbol,name,"SELL",sell,rg,rr,ltp,"Previous completed week",i)

def orb(symbol,name,d,i,ltp,rr,monthly=False):
    key="M" if monthly else "W-FRI"
    x=d.copy()
    x["P"]=period_index(x.index,key)
    cur=period_index(pd.DatetimeIndex([d.index[-1]]),key)[0]
    z=days(x[x["P"]==cur])
    if i is not None and not i.empty:
        today=i.index[-1].date()
        z=z[z.index < today]
    if len(z)<2:
        return
    r=z.iloc[:2]
    hi,lo=float(r.High.max()),float(r.Low.min())
    rg=hi-lo
    strategy="Monthly ORB" if monthly else "Weekly ORB"
    if breakout_time(i,hi,"BUY") is not None:
        return sig(strategy,symbol,name,"BUY",hi,rg,rr,ltp,"First 2 completed days",i)
    if breakout_time(i,lo,"SELL") is not None:
        return sig(strategy,symbol,name,"SELL",lo,rg,rr,ltp,"First 2 completed days",i)
