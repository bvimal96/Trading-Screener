import requests,pandas as pd
from io import StringIO

INDEXES={"NIFTY":{"name":"NIFTY 50","yahoo":"^NSEI","kind":"INDEX"},
"BANKNIFTY":{"name":"BANKNIFTY","yahoo":"^NSEBANK","kind":"INDEX"}}
URLS=[
 "https://www.nseindia.com/products-services/equity-derivatives-list-underlyings-information?F=4YV4",
 "https://www.nseindia.com/static/products-services/equity-derivatives-list-underlyings-information",
]
# Fallback universe based on NSE's published individual-security F&O list.
# NSE remains the preferred source; fallback keeps the scanner populated if NSE blocks Render.
FALLBACK="""AARTIIND ABB ABBOTINDIA ACC ADANIENT ADANIPORTS ABCAPITAL ABFRL ALKEM AMBUJACEM APOLLOHOSP APOLLOTYRE ASHOKLEY ASIANPAINT ASTRAL ATUL AUBANK AUROPHARMA AXISBANK BAJAJ-AUTO BAJFINANCE BAJAJFINSV BALKRISIND BALRAMCHIN BANDHANBNK BANKBARODA BATAINDIA BERGEPAINT BEL BHARATFORG BHEL BPCL BHARTIARTL BIOCON BSOFT BOSCHLTD BRITANNIA CANFINHOME CANBK CHAMBLFERT CHOLAFIN CIPLA CUB COALINDIA COFORGE COLPAL CONCOR COROMANDEL CROMPTON CUMMINSIND DABUR DALBHARAT DEEPAKNTR DELTACORP DIVISLAB DIXON DLF LALPATHLAB DRREDDY EICHERMOT ESCORTS EXIDEIND GAIL GLENMARK GMRINFRA GODREJCP GODREJPROP GRANULES GRASIM GUJGASLTD GNFC HAVELLS HCLTECH HDFCAMC HDFCBANK HDFCLIFE HEROMOTOCO HINDALCO HAL HINDCOPPER HINDPETRO HINDUNILVR HDFC ICICIBANK ICICIGI ICICIPRULI IDFCFIRSTB IDFC IBULHSGFIN INDIAMART IEX IOC IRCTC IGL INDUSTOWER INDUSINDBK NAUKRI INFY INTELLECT INDIGO IPCALAB ITC JINDALSTEL JKCEMENT JSWSTEEL JUBLFOOD KOTAKBANK L&TFH LTTS LTIM LT LAURUSLABS LICHSGFIN LUPIN MGL M&MFIN M&M MANAPPURAM MARICO MARUTI MFSL METROPOLIS MOTHERSON MPHASIS MRF MCX MUTHOOTFIN NATIONALUM NAVINFLUOR NESTLEIND NMDC NTPC OBEROIRLTY ONGC OFSS PAGEIND PERSISTENT PETRONET PIIND PIDILITIND PEL POLYCAB PFC POWERGRID PNB PVRINOX RAIN RBLBANK RECLTD RELIANCE SBICARD SBILIFE SHREECEM SHRIRAMFIN SIEMENS SRF SBIN SAIL SUNPHARMA SUNTV SYNGENE TATACHEM TATACOMM TCS TATACONSUM TATAMOTORS TATAPOWER TATASTEEL TECHM FEDERALBNK INDIACEM INDHOTEL RAMCOCEM TITAN TORNTPHARM TRENT TVSMOTOR ULTRACEMCO""".split()

def yahoo_symbol(s):
    return s+".NS"

def _parse(html):
    out=[]
    for t in pd.read_html(StringIO(html)):
        for c in t.columns:
            if "SYMBOL" in str(c).upper():
                for _,row in t.iterrows():
                    s=str(row[c]).strip().upper()
                    if s and s not in ("SYMBOL","NAN"):
                        name=str(row.iloc[0]).strip()
                        out.append({"symbol":s,"name":name,"yahoo":yahoo_symbol(s),"kind":"F&O"})
                break
    return out

def build_universe():
    h={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
       "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
       "Referer":"https://www.nseindia.com/"}
    out=[]
    for url in URLS:
        try:
            s=requests.Session(); s.headers.update(h)
            s.get("https://www.nseindia.com/",timeout=10)
            r=s.get(url,timeout=20); r.raise_for_status()
            out=_parse(r.text)
            if len(out)>=100: break
        except Exception:
            continue
    if len(out)<100:
        out=[{"symbol":s,"name":s,"yahoo":yahoo_symbol(s),"kind":"F&O"} for s in FALLBACK]
    d={x["symbol"]:x for x in out if x["symbol"] not in ("NIFTY","BANKNIFTY")}
    return list(INDEXES.values())+list(d.values())
