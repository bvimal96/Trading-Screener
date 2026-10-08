import pandas as pd

def days(d):
    x=d.copy(); x["D"]=x.index.date
    return x.groupby("D").agg(Open=("Open","first"),High=("High","max"),Low=("Low","min"),Close=("Close","last"))

def session_intraday(i):
    if i is None or i.empty:return i
    x=i.copy(); x["D"]=x.index.date
    return x[x["D"]==x["D"].iloc[-1]]

def crossed(i, level, side):
    x=session_intraday(i)
    if x is None or len(x)<2:return False
    if side=="BUY":
        return bool(((x["High"].shift(1)<=level) & (x["High"]>level)).any())
    return bool(((x["Low"].shift(1)>=level) & (x["Low"]<level)).any())

def sig(strategy,symbol,name,side,e,rg,rr,ltp,ref):
    return {"strategy":strategy,"symbol":symbol,"name":name,"side":side,"entry":round(e,2),
            "ltp":round(ltp,2),"sl":round(e-rg if side=="BUY" else e+rg,2),
            "target":round(e+rr*rg if side=="BUY" else e-rr*rg,2),"range":round(rg,2),"reference":ref}

def rolling(symbol,name,d,i,ltp,rr):
    x=days(d)
    if i is not None and not i.empty:
        today=i.index[-1].date(); x=x[x.index < today]
    if len(x)<2:return
    r=x.iloc[-2:]; hi,lo=float(r.High.max()),float(r.Low.min()); rg=hi-lo
    if crossed(i,hi,"BUY"):return sig("Rolling 2-Day",symbol,name,"BUY",hi,rg,rr,ltp,"Previous 2 completed days")
    if crossed(i,lo,"SELL"):return sig("Rolling 2-Day",symbol,name,"SELL",lo,rg,rr,ltp,"Previous 2 completed days")

def weekly(symbol,name,d,i,ltp,off,rr):
    x=d.copy(); x["W"]=x.index.to_period("W-FRI"); g=x.groupby("W").agg(High=("High","max"),Low=("Low","min"))
    if len(g)<2:return
    cur=d.index[-1].to_period("W-FRI"); p=g[g.index < cur]
    if p.empty:return
    p=p.iloc[-1]; buy=float(p.High)*(1+off); sell=float(p.Low)*(1-off); rg=buy-sell
    if crossed(i,buy,"BUY"):return sig("Weekly High/Low",symbol,name,"BUY",buy,rg,rr,ltp,"Previous completed week")
    if crossed(i,sell,"SELL"):return sig("Weekly High/Low",symbol,name,"SELL",sell,rg,rr,ltp,"Previous completed week")

def orb(symbol,name,d,i,ltp,rr,monthly=False):
    key="M" if monthly else "W-FRI"
    x=d.copy(); x["P"]=x.index.to_period(key)
    cur=d.index[-1].to_period(key); z=days(x[x["P"]==cur])
    if i is not None and not i.empty:
        today=i.index[-1].date(); z=z[z.index < today]
    # The first two completed sessions form the ORB; breakout is monitored from session 3 onward.
    if len(z)<2:return
    r=z.iloc[:2]; hi,lo=float(r.High.max()),float(r.Low.min()); rg=hi-lo
    if crossed(i,hi,"BUY"):return sig("Monthly ORB" if monthly else "Weekly ORB",symbol,name,"BUY",hi,rg,rr,ltp,"First 2 completed days")
    if crossed(i,lo,"SELL"):return sig("Monthly ORB" if monthly else "Weekly ORB",symbol,name,"SELL",lo,rg,rr,ltp,"First 2 completed days")
