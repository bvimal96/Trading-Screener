import numpy as np
import pandas as pd

from app.hourly import _closed_bars, _is_recent_signal, _supertrend


def test_closed_bars_excludes_unfinished_and_partial_close_bar():
    index = pd.DatetimeIndex([
        "2026-10-28 09:15:00+05:30",
        "2026-10-28 10:15:00+05:30",
        "2026-10-28 11:15:00+05:30",
        "2026-10-28 12:15:00+05:30",
        "2026-10-28 15:15:00+05:30",
    ])
    frame = pd.DataFrame(
        {"Open": [100] * 5, "High": [102] * 5, "Low": [99] * 5, "Close": [101] * 5},
        index=index,
    )
    now = pd.Timestamp("2026-10-28 12:00:00", tz="Asia/Kolkata")
    result = _closed_bars(frame, now=now)
    assert list(result.index) == list(index[:2])


def test_closed_bars_excludes_1515_partial_candle_even_after_close():
    index = pd.date_range("2026-10-28 09:15", periods=7, freq="h", tz="Asia/Kolkata")
    frame = pd.DataFrame(
        {"Open": np.arange(7) + 100, "High": np.arange(7) + 102,
         "Low": np.arange(7) + 99, "Close": np.arange(7) + 101},
        index=index,
    )
    now = pd.Timestamp("2026-10-28 17:00:00", tz="Asia/Kolkata")
    result = _closed_bars(frame, now=now)
    assert result.index[-1] == pd.Timestamp("2026-10-28 14:15:00", tz="Asia/Kolkata")
    assert pd.Timestamp("2026-10-28 15:15:00", tz="Asia/Kolkata") not in result.index


def test_supertrend_returns_expected_length_and_valid_values_after_atr_warmup():
    index = pd.date_range("2026-01-01", periods=40, freq="h", tz="Asia/Kolkata")
    close = pd.Series(np.linspace(100, 120, len(index)), index=index)
    frame = pd.DataFrame({
        "Open": close - 0.3,
        "High": close + 1.0,
        "Low": close - 1.0,
        "Close": close,
    }, index=index)
    result = _supertrend(frame, factor=3.0, period=10)
    assert len(result) == len(frame)
    assert result.iloc[:9].isna().all()
    assert result.iloc[9:].notna().all()
    assert np.isfinite(result.iloc[9:].to_numpy()).all()


def test_supertrend_empty_input_is_safe():
    frame = pd.DataFrame(columns=["Open", "High", "Low", "Close"])
    result = _supertrend(frame, factor=3.0, period=10)
    assert result.empty



def test_recent_signal_uses_latest_two_market_sessions_not_calendar_days():
    now = pd.Timestamp("2026-10-26 10:00:00", tz="Asia/Kolkata")  # Monday
    sessions = pd.date_range(
        "2026-10-19 09:15:00", periods=6, freq="B", tz="Asia/Kolkata"
    )
    bars = pd.DataFrame({"Close": range(len(sessions))}, index=sessions)
    assert _is_recent_signal("2026-10-26 09:15:00+05:30", now=now, available_bars=bars)
    assert _is_recent_signal("2026-10-23 14:15:00+05:30", now=now, available_bars=bars)
    assert not _is_recent_signal("2026-10-22 14:15:00+05:30", now=now, available_bars=bars)


def test_recent_signal_handles_exchange_holiday_gap_using_available_sessions():
    now = pd.Timestamp("2026-10-27 10:00:00", tz="Asia/Kolkata")
    # Assume Monday was an exchange holiday; Yahoo bars show Friday then Tuesday.
    sessions = pd.DatetimeIndex([
        "2026-10-22 09:15:00+05:30",
        "2026-10-23 09:15:00+05:30",
        "2026-10-27 09:15:00+05:30",
    ])
    bars = pd.DataFrame({"Close": [1, 2, 3]}, index=sessions)
    assert _is_recent_signal("2026-10-23 09:15:00+05:30", now=now, available_bars=bars)
    assert not _is_recent_signal("2026-10-22 09:15:00+05:30", now=now, available_bars=bars)
