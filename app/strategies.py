import pandas as pd
def days(d):
    x=d.copy(); x["D"]=x.index.date
    return x.groupby("D").agg(Open=("Open","first"),High=("High","max"),Low=("Low","min"),Close=("Close","last"))
def sig(strategy,symbol,name,side,e,rg,rr,ltp,ref):
    return {"strategy":strategy,"symbol":symbol,"name":name,"side":side,"entry":round(e,2),
            "ltp":round(ltp,2),"sl":round(e-rg if side=="BUY" else e+rg,2),
            "target":round(e+rr*rg if side=="BUY" else e-rr*rg,2),"range":round(rg,2),"reference":ref}
def rolling(symbol,name,d,ltp,rr):
    x=days(d)
    if len(x)<2:return
    r=x.iloc[-2:]; hi,lo=float(r.High.max()),float(r.Low.min()); rg=hi-lo
    if ltp>hi:return sig("Rolling 2-Day",symbol,name,"BUY",hi,rg,rr,ltp,"Previous 2 completed days")
    if ltp<lo:return sig("Rolling 2-Day",symbol,name,"SELL",lo,rg,rr,ltp,"Previous 2 completed days")
def weekly(symbol,name,d,ltp,off,rr):
    x=d.copy(); x["W"]=x.index.to_period("W-FRI"); g=x.groupby("W").agg(High=("High","max"),Low=("Low","min"))
    if len(g)<2:return
    p=g.iloc[-2]; buy=float(p.High)*(1+off); sell=float(p.Low)*(1-off); rg=buy-sell
    if ltp>buy:return sig("Weekly High/Low",symbol,name,"BUY",buy,rg,rr,ltp,"Previous completed week")
    if ltp<sell:return sig("Weekly High/Low",symbol,name,"SELL",sell,rg,rr,ltp,"Previous completed week")
def orb(symbol,name,d,ltp,rr,monthly=False):
    x=d.copy(); key="M" if monthly else "W"; x[key]=x.index.to_period("M" if monthly else "W-FRI"); cur=x.iloc[-1][key]
    z=days(x[x[key]==cur])
    if len(z)<2:return
    r=z.iloc[:2]; hi,lo=float(r.High.max()),float(r.Low.min()); rg=hi-lo
    if ltp>hi:return sig("Monthly ORB" if monthly else "Weekly ORB",symbol,name,"BUY",hi,rg,rr,ltp,"First 2 completed days")
    if ltp<lo:return sig("Monthly ORB" if monthly else "Weekly ORB",symbol,name,"SELL",lo,rg,rr,ltp,"First 2 completed days")
