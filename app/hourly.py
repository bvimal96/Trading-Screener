import os
import time
import pandas as pd
from .alerts import notify

def _closed_bars(frame, now=None):
    if frame is None or frame.empty:
        return frame
    x=frame.copy().sort_index()
    now = pd.Timestamp.now(tz="Asia/Kolkata") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("Asia/Kolkata")
    else:
        now = now.tz_convert("Asia/Kolkata")
    keep=[]
    for ts in x.index:
        local=ts.tz_convert("Asia/Kolkata") if ts.tzinfo else ts.tz_localize("Asia/Kolkata")
        minute=local.hour*60+local.minute
        complete=local+pd.Timedelta(minutes=60)<=now
        in_session=9*60+15<=minute<15*60
        aligned=(minute-(9*60+15))%60==0
        keep.append(bool(complete and in_session and aligned))
    return x.loc[keep]


def _is_recent_signal(signal_time, now=None, available_bars=None):
    """Show only signals dated today or yesterday in India.

    Do not derive freshness from the newest date present in Yahoo's response:
    stale responses can end several sessions ago and incorrectly make an old
    signal look recent relative to that stale data.
    """
    current = pd.Timestamp.now(tz="Asia/Kolkata") if now is None else pd.Timestamp(now)
    if current.tzinfo is None:
        current = current.tz_localize("Asia/Kolkata")
    else:
        current = current.tz_convert("Asia/Kolkata")

    ts = pd.Timestamp(signal_time)
    if ts.tzinfo is None:
        ts = ts.tz_localize("Asia/Kolkata")
    else:
        ts = ts.tz_convert("Asia/Kolkata")

    age_days = (current.date() - ts.date()).days
    return 0 <= age_days <= 1

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
    history=[]
    now=time.time()
    for item in universe:
        try:
            raw=data.hourly(item["yahoo"])
            bars=_closed_bars(raw)
            if bars is None or len(bars)<60:
                # Preserve last good row when Yahoo is temporarily rate-limiting.
                previous=state.get("by_symbol",{}).get(item["symbol"])
                if previous:
                    rows.append(previous)
                continue

            st=_supertrend(bars,3.0,10)
            ema=bars["Close"].ewm(span=50,adjust=False,min_periods=50).mean()
            valid=bars.copy()
            valid["_st"]=st
            valid["_ema"]=ema
            valid=valid.dropna(subset=["_st","_ema"])
            if valid.empty:
                continue

            active=None
            last_trade=None
            symbol_history=[]
            for bt,bar in valid.iterrows():
                bt_local=bt.tz_localize("Asia/Kolkata") if bt.tzinfo is None else bt.tz_convert("Asia/Kolkata")
                o,h,l,c=[float(bar[k]) for k in ("Open","High","Low","Close")]
                stv=float(bar["_st"]); emav=float(bar["_ema"])

                # A trailing stop established by the previous completed candle
                # is tested against this candle. Only after surviving it do we
                # trail the stop to the current candle's Supertrend.
                if active is not None:
                    old_stop=float(active["sl"])
                    hit=(l<=old_stop) if active["side"]=="BUY" else (h>=old_stop)
                    if hit:
                        exit_price=min(o,old_stop) if active["side"]=="BUY" else max(o,old_stop)
                        active["status"]="SL HIT"
                        active["exit_time"]=bt_local.isoformat()
                        active["exit_price"]=round(exit_price,2)
                        active["updated"]=now
                        last_trade=active
                        symbol_history.append(active)
                        active=None
                        # Avoid ambiguous same-candle re-entry after an SL touch.
                        continue
                    if active["side"]=="BUY":
                        active["sl"]=round(max(old_stop,stv),2)
                    else:
                        active["sl"]=round(min(old_stop,stv),2)
                    active["ltp"]=round(c,2)
                    active["supertrend"]=round(stv,2)
                    active["ema"]=round(emav,2)
                    active["updated"]=now
                    continue

                above=min(o,h,l,c)>stv and min(o,h,l,c)>emav
                below=max(o,h,l,c)<stv and max(o,h,l,c)<emav
                if not (above or below):
                    continue

                side="BUY" if above else "SELL"
                active={
                    "symbol":item["symbol"],"name":item["name"],
                    "strategy":"Hourly Supertrend + EMA 50","side":side,
                    "signal_time":bt_local.isoformat(),"entry":round(c,2),
                    "ltp":round(c,2),"supertrend":round(stv,2),
                    "ema":round(emav,2),"sl":round(stv,2),
                    "status":"ACTIVE","exit_time":None,"exit_price":None,
                    "signal_id":f"hourly:{item['symbol']}:{bt_local.isoformat()}:{side}",
                    "updated":now,
                    "reference":"First completed 1-hour candle with full OHLC above/below both lines"
                }
                # Alert only for signals that formed after this process started.
                if bt_local.timestamp()+3600>state.get("started_at",0) and os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
                    notify(active,os.getenv("PUBLIC_URL",""))
                last_trade=active
                symbol_history.append(dict(active))

            latest=active if active is not None else last_trade
            if latest is not None:
                rows.append(latest)
                history.extend(symbol_history)
        except Exception as exc:
            print(f"HOURLY_SYMBOL_SCAN_ERROR {item.get('symbol', item.get('yahoo'))}: {exc}", flush=True)
            previous=state.get("by_symbol",{}).get(item["symbol"])
            if previous:
                rows.append(previous)
            continue

    priority={"NIFTY":0,"BANKNIFTY":1}
    rows.sort(key=lambda item:(priority.get(item["symbol"],2),item["symbol"]))
    history.sort(key=lambda item:(item["symbol"],item["signal_time"]))
    state["rows"]=rows
    state["by_symbol"]={item["symbol"]:item for item in rows}
    state["history"]=history
    state["updated"]=now
