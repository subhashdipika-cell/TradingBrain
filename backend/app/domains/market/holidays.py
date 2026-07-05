"""
TradingBrain
Market - NSE Trading-Holiday Calendar

Refreshed once per IST day from Dhan's public holiday page
(https://dhan.co/market-holiday/) and cached to disk, so the platform
verifies "is today a market holiday?" on the first run of each day.
Only the TRADING-holiday table is parsed — the page's "Clearing Holidays"
section lists days the market still trades, so it is excluded. Falls back
to the hardcoded 2026 list when the site is unreachable.

Author: TradingBrain
"""

from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
DHAN_HOLIDAY_URL = "https://dhan.co/market-holiday/"
CACHE_FILE = Path(__file__).parent / "nse_holidays_cache.json"

NSE_HOLIDAYS_2026_FALLBACK = [
    "2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31", "2026-04-03",
    "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26", "2026-09-14",
    "2026-10-02", "2026-10-20", "2026-11-10", "2026-11-24", "2026-12-25",
]
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
_MEM: dict = {"day": None, "list": []}


def _ist_today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _fetch_from_dhan() -> list[str]:
    """Parse '26 Jan 2026'-style dates from the section BEFORE 'Clearing Holidays'."""
    req = urllib.request.Request(
        DHAN_HOLIDAY_URL, headers={"User-Agent": "Mozilla/5.0 TradingBrain"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", "replace")
    cut = re.search(r"Clearing\s+Holidays", html, re.I)
    section = html[:cut.start()] if cut else html
    out = set()
    for d, mon, y in re.findall(
            r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{4})",
            section):
        out.add(f"{int(y):04d}-{_MONTHS[mon]:02d}-{int(d):02d}")
    return sorted(out)


def holidays() -> list[str]:
    """Trading-holiday dates (YYYY-MM-DD), refreshed once per IST day."""
    today = _ist_today()
    if _MEM["day"] == today and _MEM["list"]:
        return _MEM["list"]
    cache: dict = {}
    try:
        cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    result: list[str] | None = None
    if cache.get("fetched") == today and cache.get("holidays"):
        result = cache["holidays"]
    else:
        try:
            fetched = _fetch_from_dhan()
            if fetched:
                result = fetched
                CACHE_FILE.write_text(
                    json.dumps({"fetched": today, "holidays": fetched}, indent=2),
                    encoding="utf-8")
        except Exception:
            result = None
    if not result:
        result = cache.get("holidays") or NSE_HOLIDAYS_2026_FALLBACK
    _MEM["day"] = today
    _MEM["list"] = result
    return result


def trading_day_check(moment: datetime | None = None) -> tuple[bool, str]:
    """(is_trading_day, reason). Weekends and Dhan-listed holidays are closed."""
    ist = (moment.astimezone(IST) if moment and moment.tzinfo
           else moment) or datetime.now(IST)
    day = ist.strftime("%Y-%m-%d")
    if ist.weekday() >= 5:
        return False, f"{day} is a weekend — NSE closed."
    if day in set(holidays()):
        return False, f"{day} is an NSE trading holiday (Dhan holiday calendar)."
    return True, f"{day} is a normal NSE trading day."
