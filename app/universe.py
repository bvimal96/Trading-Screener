import requests,pandas as pd
from io import StringIO

INDEXES={"NIFTY":{"symbol":"NIFTY","name":"NIFTY 50","yahoo":"^NSEI","kind":"INDEX"},
"BANKNIFTY":{"symbol":"BANKNIFTY","name":"NIFTY BANK","yahoo":"^NSEBANK","kind":"INDEX"}}

URLS=[
 "https://www.nseindia.com/products-services/equity-derivatives-list-underlyings-information?F=4YV4",
 "https://www.nseindia.com/static/products-services/equity-derivatives-list-underlyings-information",
]

SYMBOL_MAP={
    "L&TFH":"LTF",
    "TATAMOTORS":"TMPV",
    "IBULHSGFIN":"SAMMAANCAP",
}
DROP_SYMBOLS={"HDFC","IDFC"}

FALLBACK="""AARTIIND ABB ABBOTINDIA ACC ADANIENT ADANIPORTS ABCAPITAL ABFRL ALKEM AMBUJACEM APOLLOHOSP APOLLOTYRE ASHOKLEY ASIANPAINT ASTRAL ATUL AUBANK AUROPHARMA AXISBANK BAJAJ-AUTO BAJFINANCE BAJAJFINSV BALKRISIND BALRAMCHIN BANDHANBNK BANKBARODA BATAINDIA BERGEPAINT BEL BHARATFORG BHEL BPCL BHARTIARTL BIOCON BSOFT BOSCHLTD BRITANNIA CANFINHOME CANBK CHAMBLFERT CHOLAFIN CIPLA CUB COALINDIA COFORGE COLPAL CONCOR COROMANDEL CROMPTON CUMMINSIND DABUR DALBHARAT DEEPAKNTR DELTACORP DIVISLAB DIXON DLF LALPATHLAB DRREDDY EICHERMOT ESCORTS EXIDEIND GAIL GLENMARK GMRINFRA GODREJCP GODREJPROP GRANULES GRASIM GUJGASLTD GNFC HAVELLS HCLTECH HDFCAMC HDFCBANK HDFCLIFE HEROMOTOCO HAL HINDALCO HINDCOPPER HINDPETRO HINDUNILVR ICICIBANK ICICIGI ICICIPRULI IDFCFIRSTB INDIAMART IEX IOC IRCTC IGL INDUSTOWER INDUSINDBK NAUKRI INFY INDHOTEL INDIGO IPCALAB ITC JINDALSTEL JKCEMENT JSWSTEEL JUBLFOOD KOTAKBANK LT LTF LTTS LTIM LAURUSLABS LICHSGFIN LUPIN MGL M&MFIN M&M MANAPPURAM MARICO MARUTI MFSL METROPOLIS MOTHERSON MPHASIS MRF MCX MUTHOOTFIN NATIONALUM NAVINFLUOR NESTLEIND NMDC NTPC OBEROIRLTY ONGC OFSS PAGEIND PERSISTENT PETRONET PIIND PIDILITIND PEL POLYCAB PFC POWERGRID PNB PVRINOX RAIN RBLBANK RECLTD RELIANCE SBICARD SBILIFE SHREECEM SHRIRAMFIN SIEMENS SRF SBIN SAIL SAMMAANCAP SUNPHARMA SUNTV SYNGENE TATACHEM TATACOMM TCS TATACONSUM TMPV TATAPOWER TATASTEEL TECHM FEDERALBNK INDIACEM RAMCOCEM TITAN TORNTPHARM TRENT TVSMOTOR ULTRACEMCO""".split()

def normalize_symbol(s):
    s=str(s).strip().upper()
    return SYMBOL_MAP.get(s,s)

def yahoo_symbol(s):
    return normalize_symbol(s)+".NS"

def _parse(html):
    out=[]
    for t in pd.read_html(StringIO(html)):
        for c in t.columns:
            if "SYMBOL" in str(c).upper():
                for _,row in t.iterrows():
                    raw=str(row[c]).strip().upper()
                    if not raw or raw in ("SYMBOL","NAN"):
                        continue
                    s=normalize_symbol(raw)
                    if s in DROP_SYMBOLS:
                        continue
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
            if len(out)>=100:
                break
        except Exception:
            continue
    if len(out)<100:
        out=[{"symbol":normalize_symbol(s),"name":normalize_symbol(s),
              "yahoo":yahoo_symbol(s),"kind":"F&O"} for s in FALLBACK]
    d={x["symbol"]:x for x in out if x["symbol"] not in ("NIFTY","BANKNIFTY")}
    return list(INDEXES.values())+list(d.values())
