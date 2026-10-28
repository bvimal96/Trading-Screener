import os
import time
import pandas as pd
from .alerts import notify

def _closed_bars(frame):
    if frame is None or frame.empty:
        return frame
    x=frame.copy().sort_index()
    now=pd.Timestamp.now(tz="Asia/Kolkata")
    keep=[]
    for ts in x.index:
        local=ts.tz_convert("Asia/Kolkata") if ts.tzinfo else ts.tz_localize("Asia/Kolkata")
        minute=local.hour*60+local.minute
        complete=local+pd.Timedelta(minutes=60)<=now
        in_session=9*60+15<=minute<15*60+15
        aligned=(minute-(9*60+15))%60==0
        keep.append(bool(complete and in_session and aligned))
    return x.loc[keep]

def _supertrend(frame,factor=3.0,period=10):
    """Return TSL using the user's supplied Supertrend formula.

    Up = hl2 - factor * ATR(period)
    Dn = hl2 + factor * ATR(period)
    TrendUp = close[1] > TrendUp[1] ? max(Up, TrendUp[1]) : Up
    TrendDown = close[1] < TrendDown[1] ? min(Dn, TrendDown[1]) : Dn
    Trend = close > TrendDown[1] ? 1 : close < TrendUp[1] ? -1 : nz(Trend[1], 1)
    TSL = Trend == 1 ? TrendUp : TrendDown
    """
    x = frame.copy()
    if x.empty:
        return pd.Series(index=x.index, dtype=float)

    high = x["High"].astype(float)
    low = x["Low"].astype(float)
    close = x["Close"].astype(float)
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Pine's ATR uses Wilder's RMA: SMA seed, then recursive smoothing.
    atr = pd.Series(float("nan"), index=x.index, dtype=float)
    if len(tr) >= period:
        first_atr_idx = period - 1
        atr.iloc[first_atr_idx] = tr.iloc[:period].mean()
        for i in range(first_atr_idx + 1, len(tr)):
            atr.iloc[i] = ((period - 1) * atr.iloc[i - 1] + tr.iloc[i]) / period

    hl2 = (high + low) / 2.0
    up = hl2 - factor * atr
    dn = hl2 + factor * atr

    trend_up = pd.Series(float("nan"), index=x.index, dtype=float)
    trend_down = pd.Series(float("nan"), index=x.index, dtype=float)
    trend = pd.Series(1, index=x.index, dtype=int)

    for i in range(len(x)):
        if pd.isna(atr.iloc[i]):
            continue

        # First valid ATR row initializes the bands. There is no previous band yet.
        if i == 0 or pd.isna(trend_up.iloc[i - 1]) or pd.isna(trend_down.iloc[i - 1]):
            trend_up.iloc[i] = up.iloc[i]
            trend_down.iloc[i] = dn.iloc[i]
            trend.iloc[i] = 1 if i == 0 else trend.iloc[i - 1]
            continue

        prev_up = trend_up.iloc[i - 1]
        prev_down = trend_down.iloc[i - 1]
        prev_close_value = close.iloc[i - 1]

        trend_up.iloc[i] = (
            max(up.iloc[i], prev_up)
            if prev_close_value > prev_up
            else up.iloc[i]
        )
        trend_down.iloc[i] = (
            min(dn.iloc[i], prev_down)
            if prev_close_value < prev_down
            else dn.iloc[i]
        )

        if close.iloc[i] > prev_down:
            trend.iloc[i] = 1
        elif close.iloc[i] < prev_up:
            trend.iloc[i] = -1
        else:
            trend.iloc[i] = trend.iloc[i - 1] if i > 0 else 1

    tsl = pd.Series(float("nan"), index=x.index, dtype=float)
    tsl.loc[trend == 1] = trend_up.loc[trend == 1]
    tsl.loc[trend == -1] = trend_down.loc[trend == -1]
    return tsl

def scan_hourly(app,universe,state):
    data=app.state.data
    state["error"]=None
    symbols=[item["yahoo"] for item in universe]
    try:
        data.prefetch_hourly(symbols)
    except Exception as exc:
        state["error"]=str(exc)
    rows=[]
    now=time.time()
    for item in universe:
        try:
            raw=data.hourly(item["yahoo"])
            bars=_closed_bars(raw)
            if bars is None or len(bars)<60:
                continue
            st=_supertrend(bars,3.0,10)
            ema=bars["Close"].ewm(span=50,adjust=False,min_periods=50).mean()
            bar=bars.iloc[-1]
            stv=float(st.iloc[-1]); emav=float(ema.iloc[-1])
            if pd.isna(stv) or pd.isna(emav):
                continue
            o,h,l,c=[float(bar[k]) for k in ("Open","High","Low","Close")]
            above=min(o,h,l,c)>stv and min(o,h,l,c)>emav
            below=max(o,h,l,c)<stv and max(o,h,l,c)<emav
            if not above and not below:
                continue
            side="BUY" if above else "SELL"
            bt=bars.index[-1]
            bt=bt.tz_localize("Asia/Kolkata") if bt.tzinfo is None else bt.tz_convert("Asia/Kolkata")
            sid=f"hourly:{item['symbol']}:{bt.isoformat()}:{side}"
            signal={"symbol":item["symbol"],"name":item["name"],"strategy":"Hourly Supertrend + EMA 50","side":side,
                "signal_time":bt.isoformat(),"entry":round(c,2),"ltp":round(c,2),"supertrend":round(stv,2),
                "ema":round(emav,2),"signal_id":sid,"updated":now,
                "reference":"Completed 1-hour candle; full OHLC above/below both lines"}
            rows.append(signal)
            # Do not replay a signal from a candle that was already closed before this
            # process started (important on free instances that can sleep/restart).
            candle_closed_at=bt.timestamp()+3600
            if candle_closed_at > state.get("started_at", 0) and os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
                notify(signal,os.getenv("PUBLIC_URL",""))
        except Exception:
            continue
    priority={"NIFTY":0,"BANKNIFTY":1}
    rows.sort(key=lambda item:(priority.get(item["symbol"],2),item["symbol"]))
    state["rows"]=rows
    state["updated"]=now
