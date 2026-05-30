"""Look-ahead section: manually-curated upcoming family events.

Reads `look_ahead.yaml` at repo root. Schema:

    - date: 2026-06-15      # required, YYYY-MM-DD
      title: Anniversary    # required
      notes: Reservation 7pm at...  # optional

Events within the next 90 days (configurable) are shown, sorted by date.
Past events drop off automatically.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import yaml

from sections._common import LOCAL_TZ, section_card, section_error

LOOK_AHEAD_FILE = Path(__file__).resolve().parent.parent / "look_ahead.yaml"
WINDOW_DAYS = 90


def _load_events() -> list[dict]:
    if not LOOK_AHEAD_FILE.exists():
        return []
    with LOOK_AHEAD_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    out = []
    for entry in data:
        d = entry.get("date")
        if isinstance(d, str):
            d = date.fromisoformat(d)
        out.append({"date": d, "title": entry["title"], "notes": entry.get("notes", "")})
    return out


def _days_away_label(target: date, today: date) -> str:
    delta = (target - today).days
    if delta == 0: return "Today"
    if delta == 1: return "Tomorrow"
    if delta < 7:  return f"in {delta} days"
    if delta < 14: return "next week"
    weeks = delta // 7
    if delta < 60: return f"in {weeks} weeks"
    return f"in {delta // 30} months"


def render() -> str:
    try:
        from datetime import datetime
        today = datetime.now(LOCAL_TZ).date()
        horizon = today + timedelta(days=WINDOW_DAYS)
        events = [e for e in _load_events() if today <= e["date"] <= horizon]
        events.sort(key=lambda e: e["date"])
    except Exception as e:
        return section_error("Look Ahead", f"Next {WINDOW_DAYS} days", str(e))

    if not events:
        body = """<div style="padding:8px 0;font-size:13px;color:#7B8794;">
          Nothing on the calendar in the next 90 days. Add events to <code>look_ahead.yaml</code>.
        </div>"""
        return section_card("Look Ahead", "Next 90 Days", body)

    rows = []
    for e in events:
        d = e["date"]
        when_main = d.strftime("%a, %b %d")
        when_sub = _days_away_label(d, today)
        notes_html = f"""<div style="font-size:12px;color:#7B8794;margin-top:2px;">{e['notes']}</div>""" if e["notes"] else ""
        rows.append(f"""
        <tr>
          <td style="padding:14px 12px 14px 0;border-bottom:1px solid #EDF0F3;vertical-align:top;width:140px;white-space:nowrap;">
            <div style="font-size:14px;font-weight:700;color:#1F2933;">{when_main}</div>
            <div style="font-size:11px;color:#9AA5B1;text-transform:uppercase;letter-spacing:0.5px;margin-top:2px;">{when_sub}</div>
          </td>
          <td style="padding:14px 0;border-bottom:1px solid #EDF0F3;vertical-align:top;">
            <div style="font-size:15px;font-weight:600;color:#1F2933;">{e['title']}</div>
            {notes_html}
          </td>
        </tr>""")

    body = f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{''.join(rows)}</table>"""
    return section_card("Look Ahead", f"Next {WINDOW_DAYS} Days", body)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(render())
