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
    return x[x["D"]==x["D"].iloc[-1]]

def crossed(i, level, side):
    """
    Detect a real breakout during today's completed/available 5-minute session.
    Also accepts a gap through the level on the first available bar.
    """
    x=session_intraday(i)
    if x is None or x.empty:
        return False

    if side=="BUY":
        normal=((x["High"].shift(1)<=level) & (x["High"]>level))
        gap=((x["Open"]>level) & (x.index==x.index[0]))
        return bool((normal | gap).any())

    normal=((x["Low"].shift(1)>=level) & (x["Low"]<level))
    gap=((x["Open"]<level) & (x.index==x.index[0]))
    return bool((normal | gap).any())

def sig(strategy,symbol,name,side,e,rg,rr,ltp,ref):
    if side=="BUY":
        sl=e-rg
        target=e+rr*rg
        status="SL HIT" if ltp<=sl else ("TARGET HIT" if ltp>=target else "OPEN")
    else:
        sl=e+rg
        target=e-rr*rg
        status="SL HIT" if ltp>=sl else ("TARGET HIT" if ltp<=target else "OPEN")

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
        "status":status
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

    if crossed(i,hi,"BUY"):
        return sig("Rolling 2-Day",symbol,name,"BUY",hi,rg,rr,ltp,"Previous 2 completed days")
    if crossed(i,lo,"SELL"):
        return sig("Rolling 2-Day",symbol,name,"SELL",lo,rg,rr,ltp,"Previous 2 completed days")

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

    if crossed(i,buy,"BUY"):
        return sig("Weekly High/Low",symbol,name,"BUY",buy,rg,rr,ltp,"Previous completed week")
    if crossed(i,sell,"SELL"):
        return sig("Weekly High/Low",symbol,name,"SELL",sell,rg,rr,ltp,"Previous completed week")

def orb(symbol,name,d,i,ltp,rr,monthly=False):
    key="M" if monthly else "W-FRI"
    x=d.copy()
    x["P"]=period_index(x.index,key)

    cur=period_index(pd.DatetimeIndex([d.index[-1]]),key)[0]
    z=days(x[x["P"]==cur])

    if i is not None and not i.empty:
        today=i.index[-1].date()
        z=z[z.index < today]

    # First two completed sessions form the ORB; breakout is monitored from session 3 onward.
    if len(z)<2:
        return

    r=z.iloc[:2]
    hi,lo=float(r.High.max()),float(r.Low.min())
    rg=hi-lo

    strategy="Monthly ORB" if monthly else "Weekly ORB"
    if crossed(i,hi,"BUY"):
        return sig(strategy,symbol,name,"BUY",hi,rg,rr,ltp,"First 2 completed days")
    if crossed(i,lo,"SELL"):
        return sig(strategy,symbol,name,"SELL",lo,rg,rr,ltp,"First 2 completed days")
