import asyncio,time,os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI,Query,Request
from fastapi.responses import HTMLResponse,JSONResponse,StreamingResponse
from io import BytesIO
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from fastapi.staticfiles import StaticFiles
from .config import settings
from .universe import build_universe
from .data import YahooData
from .strategies import rolling,weekly,orb
from .alerts import notify

STATE={"universe":[],"rows":[],"updated":None,"error":None,"previous":set(),"scanning":False}

def calculate(app):
    rows=[]; p=app.state.data
    STATE["scanning"]=True
    try:
        symbols=[u["yahoo"] for u in STATE["universe"]]
        p.prefetch(symbols)
        usable=0
        for u in STATE["universe"]:
            try:
                intr=p.intraday(u["yahoo"])
                d=p.daily(u["yahoo"])
                if intr.empty or d.empty:
                    continue
                usable+=1
                ltp,ts=float(intr.iloc[-1].Close),intr.index[-1]

                ss=[
                    rolling(u["symbol"],u["name"],d,intr,ltp,settings.rolling_rr),
                    weekly(u["symbol"],u["name"],d,intr,ltp,settings.weekly_offset,settings.weekly_rr),
                    orb(u["symbol"],u["name"],d,intr,ltp,settings.weekly_orb_rr,False),
                    orb(u["symbol"],u["name"],d,intr,ltp,settings.monthly_orb_rr,True)
                ]
                for s in ss:
                    if s:
                        s["updated"]=ts.isoformat() if ts else None
                        rows.append(s)
                        k=f"{s['symbol']}|{s['strategy']}|{s['side']}"
                        if k not in STATE["previous"]:
                            notify(s,os.getenv("PUBLIC_URL",""))
                            STATE["previous"].add(k)
            except Exception:
                continue
        active={f"{x['symbol']}|{x['strategy']}|{x['side']}" for x in rows}
        STATE["previous"] &= active
        STATE["rows"]=rows
        STATE["updated"]=time.time()
        print(f"SCAN_OK universe={len(STATE['universe'])} usable={usable} signals={len(rows)}",flush=True)
    finally:
        STATE["scanning"]=False

async def worker(app):
    while True:
        try:
            if not STATE["universe"]:
                STATE["universe"]=await asyncio.to_thread(build_universe)
            await asyncio.to_thread(calculate,app)
            STATE["error"]=None
        except Exception as e:
            STATE["error"]=str(e)
            print(f"SCAN_ERROR {e}",flush=True)
        await asyncio.sleep(settings.poll_seconds)

@asynccontextmanager
async def lifespan(app):
    app.state.data=YahooData(settings.timezone)
    t=asyncio.create_task(worker(app))
    yield
    t.cancel()

app=FastAPI(title="NIFTY Live Breakout Screener",lifespan=lifespan)
app.mount("/static",StaticFiles(directory=Path(__file__).parent.parent/"static"),name="static")

@app.get("/",response_class=HTMLResponse)
def home():
    return (Path(__file__).parent.parent/"static/index.html").read_text()

@app.get("/health")
def health():
    return {"ok":True,"updated":STATE["updated"],"universe":len(STATE["universe"]),
            "signals":len(STATE["rows"]),"scanning":STATE["scanning"],"error":STATE["error"]}

@app.get("/api/status")
def status():
    return {"updated":STATE["updated"],"universe":len(STATE["universe"]),
            "signals":len(STATE["rows"]),"scanning":STATE["scanning"],"error":STATE["error"]}

@app.get("/api/signals")
def signals(strategy:str|None=Query(None),side:str|None=Query(None)):
    r=STATE["rows"]
    if strategy:
        r=[x for x in r if x["strategy"]==strategy]
    if side:
        r=[x for x in r if x["side"]==side]
    return {"updated":STATE["updated"],"data":r}

@app.post("/api/refresh")
def refresh():
    STATE["universe"]=build_universe()
    calculate(app)
    return {"ok":True,"universe":len(STATE["universe"]),"signals":len(STATE["rows"])}


@app.get("/api/export.xlsx")
def export_xlsx(
    strategy:str|None=Query(None),
    side:str|None=Query(None),
    status:str|None=Query(None),
    search:str|None=Query(None)
):
    rows=list(STATE["rows"])
    if strategy:
        rows=[x for x in rows if x.get("strategy")==strategy]
    if side:
        rows=[x for x in rows if x.get("side")==side]
    if status:
        rows=[x for x in rows if x.get("status")==status]
    if search:
        q=search.strip().upper()
        rows=[x for x in rows if q in str(x.get("symbol","")).upper() or q in str(x.get("name","")).upper()]

    columns=[
        ("Symbol","symbol"),("Company Name","name"),("Strategy","strategy"),
        ("Side","side"),("Entry Price","entry"),("LTP","ltp"),("P&L (Points)","pnl"),
        ("Stop Loss","sl"),("Target","target"),("Range","range"),
        ("Status","status"),
        ("Entry Time","entry_time"),("Event Time","event_time"),("Last Updated","updated")
    ]
    strategy_labels={
        "Rolling 2-Day":"Roll Intra Day",
        "Weekly High/Low":"Week HL- EOW",
        "Weekly ORB":"Week 2 Day",
        "Monthly ORB":"Month 2 Day"
    }
    wb=Workbook()
    ws=wb.active
    ws.title="Screener Signals"
    ws.append([c[0] for c in columns])
    for cell in ws[1]:
        cell.font=Font(bold=True,color="FFFFFF")
        cell.fill=PatternFill("solid",fgColor="1F4E78")
        cell.alignment=Alignment(horizontal="center")
    for row in rows:
        values=[]
        for _,key in columns:
            if key=="pnl":
                try:
                    entry=float(row.get("entry")); ltp=float(row.get("ltp"))
                    value=round((ltp-entry) if row.get("side")=="BUY" else (entry-ltp),2)
                except (TypeError,ValueError):
                    value=None
            elif key=="strategy":
                value=strategy_labels.get(row.get(key),row.get(key))
            else:
                value=row.get(key)
            values.append(value)
        ws.append(values)
    ws.freeze_panes="A2"
    ws.auto_filter.ref=ws.dimensions
    for col in ws.columns:
        letter=col[0].column_letter
        max_len=max((len(str(cell.value or "")) for cell in col),default=10)
        ws.column_dimensions[letter].width=min(max(max_len+2,12),32)
    ws.sheet_view.showGridLines=False
    buffer=BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    filename="screener_signals_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":f'attachment; filename="{filename}"'}
    )

@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(request:Request):
    return JSONResponse({"ok":True})
