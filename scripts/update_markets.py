#!/usr/bin/env python3
"""Fetch end-of-day market data for each sector vs the Nifty 50.

Runs in GitHub Actions at 4:00 PM IST on weekdays (after NSE closes at 3:30 PM).
Reads  src/data/market-config.json
Writes src/data/market-snapshot.json

For each sector it builds a % change series for 1D (5-minute intraday), 1M, 6M and 1Y,
either from an official index (e.g. ^CNXAUTO) or from an equal-weighted basket of
listed companies, plus the same series for the Nifty 50 benchmark.
Uses only the Python standard library.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "src" / "data" / "market-config.json"
OUT = ROOT / "src" / "data" / "market-snapshot.json"
IST = timezone(timedelta(hours=5, minutes=30))

RANGES = {"1D": ("5d", "5m"), "1M": ("1mo", "1d"), "6M": ("6mo", "1d"), "1Y": ("1y", "1d")}
HOSTS = ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

errors: list[str] = []


def fetch_chart(symbol: str, rng: str, interval: str) -> dict | None:
    q = urllib.parse.urlencode({"range": rng, "interval": interval, "includePrePost": "false"})
    path = f"/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}?{q}"
    last = ""
    for attempt in range(3):
        for host in HOSTS:
            try:
                req = urllib.request.Request(host + path, headers={"User-Agent": UA, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = json.load(r)
                res = (data.get("chart") or {}).get("result") or []
                if res:
                    return res[0]
                last = str((data.get("chart") or {}).get("error"))
            except Exception as e:  # network / HTTP errors
                last = str(e)
        time.sleep(1.5 * (attempt + 1))
    errors.append(f"{symbol} {rng}: {last[:120]}")
    return None


def to_series(res: dict, intraday: bool) -> tuple[list[list], float | None]:
    """Return [[unix_ts, pct], ...] and the last pct.

    intraday=True: data covers several sessions (5d, 5-minute bars). The base is the
    last close of the previous session and only the latest session's bars are kept,
    so the 1D change matches the usual "vs previous close" figure.
    Otherwise the base is the first close in the range.
    """
    ts = res.get("timestamp") or []
    closes = (((res.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    pts = [(t, c) for t, c in zip(ts, closes) if c is not None]
    if not pts:
        return [], None
    if intraday:
        day = lambda t: datetime.fromtimestamp(t, IST).date()
        last_day = day(pts[-1][0])
        prev = [p for p in pts if day(p[0]) < last_day]
        today = [p for p in pts if day(p[0]) == last_day]
        if not prev or not today:
            return [], None
        base = prev[-1][1]
        pts = today
    else:
        base = pts[0][1]
    series = [[int(t), round((c / base - 1) * 100, 3)] for t, c in pts]
    return series, series[-1][1]


def basket_series(members: list[list[list]], grid: list[int]) -> list[list]:
    """Equal-weight average of member % series on the benchmark's time grid (forward-filled)."""
    out = []
    idx = [0] * len(members)
    lastv: list[float | None] = [None] * len(members)
    for t in grid:
        vals = []
        for i, s in enumerate(members):
            while idx[i] < len(s) and s[idx[i]][0] <= t:
                lastv[i] = s[idx[i]][1]
                idx[i] += 1
            if lastv[i] is not None:
                vals.append(lastv[i])
        if vals:
            out.append([t, round(sum(vals) / len(vals), 3)])
    return out


def main() -> int:
    cfg = json.loads(CONFIG.read_text())
    bench_sym = cfg["benchmark"]["symbol"]

    bench: dict[str, tuple[list, float | None]] = {}
    for label, (rng, iv) in RANGES.items():
        res = fetch_chart(bench_sym, rng, iv)
        if res:
            bench[label] = to_series(res, label == "1D")
    if "1D" not in bench or not bench["1D"][0]:
        print("ERROR: could not fetch the Nifty 50; leaving snapshot unchanged.", errors, file=sys.stderr)
        return 1

    session = datetime.fromtimestamp(bench["1D"][0][-1][0], IST).strftime("%Y-%m-%d")
    snapshot = {
        "generatedAt": datetime.now(IST).isoformat(timespec="minutes"),
        "session": session,
        "benchmark": cfg["benchmark"]["name"],
        "sectors": {},
        "errors": [],
    }

    for slug, sec in cfg["sectors"].items():
        ranges: dict[str, dict] = {}
        source = "basket"
        constituents = []
        # 1) Try the official index if one is configured
        if sec.get("index"):
            idx_ok = True
            for label, (rng, iv) in RANGES.items():
                res = fetch_chart(sec["index"], rng, iv)
                s, last = to_series(res, label == "1D") if res else ([], None)
                if len(s) < (10 if label == "1D" else 5):  # feed incomplete -> use the basket instead
                    idx_ok = False
                    break
                ranges[label] = {"sector": s, "sectorChange": last}
            if idx_ok:
                source = "index"
            else:
                ranges = {}
        # 2) Basket (always fetched for the constituent table; used for the line if no index)
        member_series: dict[str, dict[str, list]] = {label: [] for label in RANGES}
        for m in sec["basket"]:
            day_change = None
            for label, (rng, iv) in RANGES.items():
                if source == "index" and label != "1D":
                    continue
                res = fetch_chart(m["symbol"], rng, iv)
                if not res:
                    continue
                s, last = to_series(res, label == "1D")
                if s:
                    member_series[label].append(s)
                    if label == "1D":
                        day_change = last
                time.sleep(0.2)
            constituents.append({"name": m["name"], "symbol": m["symbol"].replace(".NS", ""), "dayChange": day_change})
        if source == "basket":
            for label in RANGES:
                grid = [p[0] for p in bench.get(label, ([], None))[0]]
                s = basket_series(member_series[label], grid) if member_series[label] and grid else []
                if s:
                    ranges[label] = {"sector": s, "sectorChange": s[-1][1], "members": len(member_series[label])}
        for label, r in ranges.items():
            b, blast = bench.get(label, ([], None))
            r["nifty"] = b
            r["niftyChange"] = blast
        constituents.sort(key=lambda c: (c["dayChange"] is None, -(c["dayChange"] or 0)))
        snapshot["sectors"][slug] = {
            "name": sec["name"] if source == "index" else sec.get("basketName", sec["name"]),
            "note": sec["note"],
            "source": source,
            "ranges": ranges,
            "constituents": constituents,
        }
        print(f"{slug}: source={source}, ranges={list(ranges)}, constituents with data="
              f"{sum(c['dayChange'] is not None for c in constituents)}/{len(constituents)}")

    snapshot["errors"] = errors[:50]
    OUT.write_text(json.dumps(snapshot, separators=(",", ":")) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)} for session {session}; {len(errors)} fetch error(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
