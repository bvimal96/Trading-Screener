import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.data import YahooData
from app.hourly import scan_hourly
from app.universe import build_universe

STATE = {"universe": [], "rows": [], "updated": None, "error": None, "started_at": time.time()}


async def worker(app):
    while True:
        try:
            if not STATE["universe"]:
                STATE["universe"] = await asyncio.to_thread(build_universe)
            await asyncio.to_thread(scan_hourly, app, STATE["universe"], STATE)
            STATE["error"] = STATE.get("error")
        except Exception as exc:
            STATE["error"] = str(exc)
            print(f"HOURLY_SCAN_ERROR {exc}", flush=True)
        await asyncio.sleep(max(60, int(os.getenv("POLL_SECONDS", "300"))))


@asynccontextmanager
async def lifespan(app):
    app.state.data = YahooData()
    task = asyncio.create_task(worker(app))
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Hourly Supertrend Screener", lifespan=lifespan)
STATIC = Path(__file__).parent.parent / "hourly_static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", response_class=HTMLResponse)
def home():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    return {
        "ok": True,
        "universe": len(STATE["universe"]),
        "signals": len(STATE["rows"]),
        "updated": STATE["updated"],
        "error": STATE["error"],
    }


@app.get("/api/hourly-signals")
def hourly_signals(side: str | None = Query(None), search: str | None = Query(None)):
    rows = list(STATE["rows"])
    if side:
        rows = [row for row in rows if row["side"] == side.upper()]
    if search:
        query = search.strip().upper()
        rows = [row for row in rows if query in row["symbol"].upper() or query in row["name"].upper()]
    priority = {"NIFTY": 0, "BANKNIFTY": 1}
    rows.sort(key=lambda row: (priority.get(row["symbol"], 2), row["symbol"]))
    return {"updated": STATE["updated"], "error": STATE["error"], "data": rows}
