import os, time, requests
from pathlib import Path

STATE_FILE=Path(os.getenv("ALERT_STATE_FILE","/tmp/alert_state.txt"))
COOLDOWN=int(os.getenv("ALERT_COOLDOWN_MINUTES","120"))*60

def _key(s):
    return f"{s['symbol']}|{s['strategy']}|{s['side']}"

def should_alert(s):
    key=_key(s)
    now=time.time()
    data={}
    if STATE_FILE.exists():
        for line in STATE_FILE.read_text().splitlines():
            try:k,t=line.split("|",1); data[k]=float(t)
            except:pass
    if now-data.get(key,0)<COOLDOWN:return False
    data[key]=now
    STATE_FILE.write_text("\n".join(f"{k}|{v}" for k,v in data.items()))
    return True

def format_alert(s, url=""):
    icon="🟢 BUY" if s["side"]=="BUY" else "🔴 SELL"
    return (
        f"{icon}\n"
        f"📌 {s['symbol']} — {s['strategy']}\n"
        f"Entry: {s['entry']}\n"
        f"LTP: {s['ltp']}\n"
        f"SL: {s['sl']}\n"
        f"Target: {s['target']}\n"
        f"Range: {s['range']}\n"
        f"Reference: {s['reference']}"
        + (f"\n🌐 {url}" if url else "")
    )

def telegram_send(text):
    token=os.getenv("TELEGRAM_BOT_TOKEN")
    chat=os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:return False
    try:
        r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         data={"chat_id":chat,"text":text},timeout=10)
        return r.ok
    except Exception:return False

def whatsapp_send(text):
    token=os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    to=os.getenv("WHATSAPP_TO")
    if not token or not phone_id or not to:return False
    try:
        url=f"https://graph.facebook.com/v23.0/{phone_id}/messages"
        h={"Authorization":f"Bearer {token}","Content-Type":"application/json"}
        body={"messaging_product":"whatsapp","to":to,
              "type":"text","text":{"body":text}}
        r=requests.post(url,headers=h,json=body,timeout=10)
        return r.ok
    except Exception:return False

def notify(s, public_url=""):
    if not should_alert(s): return {"sent":False,"reason":"cooldown"}
    msg=format_alert(s,public_url)
    tg=telegram_send(msg)
    wa=whatsapp_send(msg)
    return {"sent":tg or wa,"telegram":tg,"whatsapp":wa}
