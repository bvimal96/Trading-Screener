import requests,pandas as pd
from io import StringIO
INDEXES={"NIFTY":{"name":"NIFTY 50","yahoo":"^NSEI","kind":"INDEX"},
"BANKNIFTY":{"name":"BANKNIFTY","yahoo":"^NSEBANK","kind":"INDEX"}}
URL="https://www.nseindia.com/static/products-services/equity-derivatives-list-underlyings-information"
def yahoo_symbol(s): return s+".NS"
def build_universe():
    h={"User-Agent":"Mozilla/5.0","Referer":"https://www.nseindia.com/"}
    out=[]
    try:
        r=requests.get(URL,headers=h,timeout=15); r.raise_for_status()
        for t in pd.read_html(StringIO(r.text)):
            sc=[c for c in t.columns if "SYMBOL" in str(c).upper()]
            if not sc: continue
            for _,x in t.iterrows():
                s=str(x[sc[0]]).strip()
                n=str(x.iloc[0]).strip()
                if s and s.upper() not in ("SYMBOL","NAN"):
                    out.append({"symbol":s,"name":n,"yahoo":yahoo_symbol(s),"kind":"F&O"})
    except Exception: pass
    d={x["symbol"]:x for x in out if x["symbol"] not in INDEXES}
    return list(INDEXES.values())+list(d.values())
