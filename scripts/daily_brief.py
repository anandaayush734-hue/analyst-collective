#!/usr/bin/env python3
"""Generate today's Analyst Collective brief with Claude + web search.

Writes:  src/data/briefs/<DATE>.json   (the brief)
Updates: src/data/deals.json           (new public deals, de-duplicated)
Writes:  $PR_BODY_PATH (optional)      (review checklist used as the pull-request description)

Environment:
  ANTHROPIC_API_KEY   required
  CLAUDE_MODEL        default "claude-sonnet-5-5"
  WEB_SEARCH_TOOL     default "web_search_20250305"
  BRIEF_DATE          default: today in Asia/Kolkata (YYYY-MM-DD)
  MAX_SEARCHES        default 20
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
BRIEFS = ROOT / "src" / "data" / "briefs"
DEALS = ROOT / "src" / "data" / "deals.json"
PROMPT = ROOT / "prompts" / "daily_brief.md"

SECTORS = ["ev", "autos", "industrials", "aerospace-defence"]
TAGS = {"EV", "AUTO", "IND", "A&D", "REG", "MACRO"}
# Advice-like wording. Excludes "Buy (Indian-IDDM)" (a DAP category) and "sell-side"/"buy-side".
BANNED = re.compile(r"\b(buy(?!\s*\()(?!-side)|sell(?!-side)|hold|accumulate|target price|price target|outperform|underperform)\b", re.I)


def today_ist() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")


def previous_headlines(date: str) -> str:
    prev = sorted(p for p in BRIEFS.glob("*.json") if p.stem < date)
    if not prev:
        return "- (none)"
    data = json.loads(prev[-1].read_text())
    lines = [f"- {it['headline']}" for items in data.get("sectors", {}).values() for it in items]
    lines += [f"- {it['headline']}" for it in data.get("regulatory", [])]
    return "\n".join(lines) or "- (none)"


def call_claude(prompt: str) -> str:
    import anthropic  # only needed for the API route

    client = anthropic.Anthropic()
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
    tool = {
        "type": os.environ.get("WEB_SEARCH_TOOL", "web_search_20250305"),
        "name": "web_search",
        "max_uses": int(os.environ.get("MAX_SEARCHES", "20")),
    }
    user = {"role": "user", "content": prompt}
    assistant_so_far: list = []
    # Server-side web search can return stop_reason "pause_turn" on long runs; continue until done.
    for _ in range(6):
        messages = [user] + ([{"role": "assistant", "content": assistant_so_far}] if assistant_so_far else [])
        resp = client.messages.create(model=model, max_tokens=16000, tools=[tool], messages=messages)
        assistant_so_far += list(resp.content)
        if resp.stop_reason != "pause_turn":
            break
    # The JSON is in the final text output, after the searches.
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    if not text.strip():
        raise RuntimeError(f"No text returned (stop_reason={resp.stop_reason})")
    return text


def extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("No JSON object found in model output")
    return json.loads(text[start : end + 1])


def validate(brief: dict, date: str) -> list[str]:
    """Fix what can be fixed, return a list of warnings for the human reviewer."""
    warn: list[str] = []
    brief["date"] = date
    brief.setdefault("regulatory", [])
    brief.setdefault("keyNumbers", [])
    brief.setdefault("ticker", [])
    if not brief.get("lead", {}).get("headline"):
        raise ValueError("Missing lead headline")
    secs = brief.setdefault("sectors", {})
    for s in SECTORS:
        secs.setdefault(s, [])
        if not secs[s]:
            warn.append(f"No stories for sector '{s}'.")
    for k in list(secs):
        if k not in SECTORS:
            warn.append(f"Dropped unknown sector '{k}'.")
            del secs[k]

    def check_items(items: list, where: str) -> list:
        kept = []
        for it in items:
            missing = [f for f in ("headline", "summary", "whyItMatters", "source", "url") if not it.get(f)]
            if missing:
                warn.append(f"[{where}] dropped item missing {missing}: {it.get('headline', '?')}")
                continue
            if not str(it["url"]).startswith("http"):
                warn.append(f"[{where}] dropped item with invalid URL: {it['headline']}")
                continue
            blob = f"{it['headline']} {it['summary']} {it['whyItMatters']}"
            if BANNED.search(blob):
                warn.append(f"[{where}] contains advice-like wording, please review: {it['headline']}")
            kept.append(it)
        return kept

    for s in SECTORS:
        secs[s] = check_items(secs[s], s)
    brief["regulatory"] = check_items(brief["regulatory"], "regulatory")
    brief["ticker"] = [t for t in brief["ticker"] if t.get("text")]
    for t in brief["ticker"]:
        if t.get("tag") not in TAGS:
            t["tag"] = "MACRO"
    return warn


def merge_deals(new: list) -> int:
    existing = json.loads(DEALS.read_text()) if DEALS.exists() else []
    keys = {(d["target"].lower(), d["date"]) for d in existing}
    added = 0
    for d in new or []:
        if not all(d.get(f) for f in ("date", "sector", "type", "target", "url")) or d["sector"] not in SECTORS:
            continue
        d.setdefault("acquirer", "—"); d.setdefault("value", "Undisclosed"); d.setdefault("status", "Announced"); d.setdefault("note", "")
        if (d["target"].lower(), d["date"]) in keys:
            continue
        existing.append(d)
        keys.add((d["target"].lower(), d["date"]))
        added += 1
    existing.sort(key=lambda d: d["date"], reverse=True)
    DEALS.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n")
    return added


def main() -> int:
    date = os.environ.get("BRIEF_DATE") or today_ist()
    prompt = PROMPT.read_text().replace("{{DATE}}", date).replace("{{PREVIOUS_HEADLINES}}", previous_headlines(date))
    raw = call_claude(prompt)
    try:
        brief = extract_json(raw)
    except Exception:
        (ROOT / "last_model_output.txt").write_text(raw)
        raise
    finalize(brief, date, os.environ.get("PR_BODY_PATH"))
    return 0


def finalize(brief: dict, date: str, body_path: str | None = None) -> list[str]:
    """Validate a brief, write it, merge its deals, optionally write a PR description."""
    deals = brief.pop("deals", [])
    warnings = validate(brief, date)
    BRIEFS.mkdir(parents=True, exist_ok=True)
    out = BRIEFS / f"{date}.json"
    out.write_text(json.dumps(brief, indent=2, ensure_ascii=False) + "\n")
    added = merge_deals(deals)

    n = sum(len(v) for v in brief["sectors"].values()) + len(brief["regulatory"])
    print(f"Wrote {out.relative_to(ROOT)} with {n} stories; {added} new deal(s).")
    if body_path:
        Path(body_path).write_text(pr_body(brief, date, n, added, warnings))
    for w in warnings:
        print("WARNING:", w, file=sys.stderr)
    return warnings


def pr_body(brief: dict, date: str, n: int, added: int, warnings: list[str]) -> str:
    lines = [
        f"## Daily brief for {date}",
        f"**Lead:** {brief['lead']['headline']}",
        "",
        f"{n} stories · {added} new deal(s) added to the tracker.",
        "",
        "### Before you merge",
        "- [ ] Spot-check the key numbers against the linked sources",
        "- [ ] Nothing confidential, client-related or advice-like",
        "- [ ] Headlines read well (edit in the *Files changed* tab if needed)",
    ]
    if warnings:
        lines += ["", "### Automated warnings"] + [f"- ⚠️ {w}" for w in warnings]
    lines += ["", "### Stories"]
    for s in SECTORS + ["regulatory"]:
        items = brief["regulatory"] if s == "regulatory" else brief["sectors"][s]
        for it in items:
            lines.append(f"- **{s}**: [{it['headline']}]({it['url']}) ({it['source']})")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
