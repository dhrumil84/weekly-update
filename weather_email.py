"""Weekly weather forecast emailer.

Fetches a 7-day forecast from Open-Meteo for Anaheim, CA and emails an
HTML digest via Gmail SMTP.

Run modes:
  python weather_email.py            # fetch + send
  python weather_email.py --dry-run  # fetch + write preview.html, do not send
  python weather_email.py --force    # skip the "is it ~9pm Pacific?" guard
"""
from __future__ import annotations

import argparse
import os
import smtplib
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from zoneinfo import ZoneInfo

# --- Config -----------------------------------------------------------------

LATITUDE = 33.8366
LONGITUDE = -117.9143
LOCATION_NAME = "Anaheim, CA"
LOCAL_TZ = ZoneInfo("America/Los_Angeles")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# --- WMO weather code -> (label, inline SVG icon) ---------------------------
# Codes per https://open-meteo.com/en/docs (WMO 4677)
# SVGs are tiny, inline, and email-client safe (no external requests).

ICON_SUN = """<svg width="56" height="56" viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg"><circle cx="28" cy="28" r="10" fill="#F6B100"/><g stroke="#F6B100" stroke-width="3" stroke-linecap="round"><line x1="28" y1="6" x2="28" y2="14"/><line x1="28" y1="42" x2="28" y2="50"/><line x1="6" y1="28" x2="14" y2="28"/><line x1="42" y1="28" x2="50" y2="28"/><line x1="12" y1="12" x2="17" y2="17"/><line x1="39" y1="39" x2="44" y2="44"/><line x1="12" y1="44" x2="17" y2="39"/><line x1="39" y1="17" x2="44" y2="12"/></g></svg>"""

ICON_PARTLY = """<svg width="56" height="56" viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg"><circle cx="20" cy="20" r="8" fill="#F6B100"/><g stroke="#F6B100" stroke-width="2.5" stroke-linecap="round"><line x1="20" y1="4" x2="20" y2="9"/><line x1="4" y1="20" x2="9" y2="20"/><line x1="8" y1="8" x2="12" y2="12"/><line x1="28" y1="12" x2="32" y2="8"/></g><path d="M16 38 Q16 30 24 30 Q26 24 33 24 Q42 24 42 32 Q50 32 50 39 Q50 46 42 46 L18 46 Q12 46 12 41 Q12 38 16 38 Z" fill="#D6DEE6" stroke="#9AA5B1" stroke-width="1.5"/></svg>"""

ICON_CLOUD = """<svg width="56" height="56" viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg"><path d="M14 38 Q14 28 24 28 Q26 20 35 20 Q46 20 46 30 Q52 30 52 38 Q52 46 44 46 L16 46 Q8 46 8 40 Q8 36 14 38 Z" fill="#B8C2CC" stroke="#7B8794" stroke-width="1.5"/></svg>"""

ICON_FOG = """<svg width="56" height="56" viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg"><path d="M14 30 Q14 20 24 20 Q26 12 35 12 Q46 12 46 22 Q52 22 52 30 Q52 38 44 38 L16 38 Q8 38 8 32 Q8 28 14 30 Z" fill="#D6DEE6" stroke="#9AA5B1" stroke-width="1.5"/><g stroke="#9AA5B1" stroke-width="2.5" stroke-linecap="round"><line x1="8" y1="44" x2="48" y2="44"/><line x1="12" y1="50" x2="44" y2="50"/></g></svg>"""

ICON_RAIN = """<svg width="56" height="56" viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg"><path d="M14 24 Q14 14 24 14 Q26 6 35 6 Q46 6 46 16 Q52 16 52 24 Q52 32 44 32 L16 32 Q8 32 8 26 Q8 22 14 24 Z" fill="#9AA5B1" stroke="#52606D" stroke-width="1.5"/><g stroke="#2D9CDB" stroke-width="3" stroke-linecap="round"><line x1="18" y1="38" x2="14" y2="48"/><line x1="28" y1="38" x2="24" y2="48"/><line x1="38" y1="38" x2="34" y2="48"/></g></svg>"""

ICON_SNOW = """<svg width="56" height="56" viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg"><path d="M14 24 Q14 14 24 14 Q26 6 35 6 Q46 6 46 16 Q52 16 52 24 Q52 32 44 32 L16 32 Q8 32 8 26 Q8 22 14 24 Z" fill="#D6DEE6" stroke="#9AA5B1" stroke-width="1.5"/><g fill="#2D9CDB"><circle cx="18" cy="42" r="2.5"/><circle cx="28" cy="46" r="2.5"/><circle cx="38" cy="42" r="2.5"/></g></svg>"""

ICON_THUNDER = """<svg width="56" height="56" viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg"><path d="M14 24 Q14 14 24 14 Q26 6 35 6 Q46 6 46 16 Q52 16 52 24 Q52 32 44 32 L16 32 Q8 32 8 26 Q8 22 14 24 Z" fill="#7B8794" stroke="#3E4C59" stroke-width="1.5"/><polygon points="28,34 22,46 28,46 24,54 36,40 30,40 34,34" fill="#F6B100" stroke="#B47900" stroke-width="1"/></svg>"""

WMO = {
    0:  ("Clear",              ICON_SUN),
    1:  ("Mostly Clear",       ICON_SUN),
    2:  ("Partly Cloudy",      ICON_PARTLY),
    3:  ("Cloudy",             ICON_CLOUD),
    45: ("Fog",                ICON_FOG),
    48: ("Freezing Fog",       ICON_FOG),
    51: ("Light Drizzle",      ICON_RAIN),
    53: ("Drizzle",            ICON_RAIN),
    55: ("Heavy Drizzle",      ICON_RAIN),
    56: ("Freezing Drizzle",   ICON_RAIN),
    57: ("Freezing Drizzle",   ICON_RAIN),
    61: ("Light Rain",         ICON_RAIN),
    63: ("Rain",               ICON_RAIN),
    65: ("Heavy Rain",         ICON_RAIN),
    66: ("Freezing Rain",      ICON_RAIN),
    67: ("Freezing Rain",      ICON_RAIN),
    71: ("Light Snow",         ICON_SNOW),
    73: ("Snow",               ICON_SNOW),
    75: ("Heavy Snow",         ICON_SNOW),
    77: ("Snow Grains",        ICON_SNOW),
    80: ("Rain Showers",       ICON_RAIN),
    81: ("Rain Showers",       ICON_RAIN),
    82: ("Heavy Rain Showers", ICON_RAIN),
    85: ("Snow Showers",       ICON_SNOW),
    86: ("Heavy Snow Showers", ICON_SNOW),
    95: ("Thunderstorm",       ICON_THUNDER),
    96: ("Thunderstorm + Hail",ICON_THUNDER),
    99: ("Severe Thunderstorm",ICON_THUNDER),
}

# --- Fetch ------------------------------------------------------------------

def fetch_forecast() -> dict:
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,wind_speed_10m_max",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "America/Los_Angeles",
        "forecast_days": 7,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as resp:
        import json
        return json.loads(resp.read().decode("utf-8"))


def f_to_c(f: float) -> int:
    return round((f - 32) * 5 / 9)


# --- Render -----------------------------------------------------------------

def render_html(data: dict) -> str:
    daily = data["daily"]
    dates = daily["time"]
    codes = daily["weather_code"]
    highs = daily["temperature_2m_max"]
    lows  = daily["temperature_2m_min"]
    winds = daily["wind_speed_10m_max"]

    day_fmt = "%-d" if sys.platform != "win32" else "%#d"

    cells = []
    for i, date_str in enumerate(dates):
        d = datetime.fromisoformat(date_str)
        dow = d.strftime("%a").upper()          # MON
        date_num = d.strftime(day_fmt)          # 3
        month = d.strftime("%b")                # Jun
        is_today = (i == 0)

        label, icon = WMO.get(codes[i], ("—", ICON_CLOUD))
        hi_f = round(highs[i]); hi_c = f_to_c(highs[i])
        lo_f = round(lows[i]);  lo_c = f_to_c(lows[i])
        wind = round(winds[i])

        # Highlight today with a tinted background + accent bar.
        bg          = "#FFF8E1" if is_today else "#FFFFFF"
        accent      = "#F6B100" if is_today else "transparent"
        dow_color   = "#1F2933" if is_today else "#3E4C59"

        cells.append(f"""
        <td valign="top" width="14.28%" style="padding:0 4px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{bg};border-radius:10px;border-top:3px solid {accent};">
            <tr><td style="padding:12px 6px 4px 6px;text-align:center;">
              <div style="font-size:18px;font-weight:800;color:{dow_color};letter-spacing:1.5px;line-height:1;">{dow}</div>
              <div style="font-size:22px;font-weight:700;color:#1F2933;line-height:1.1;margin-top:6px;">{date_num}</div>
              <div style="font-size:11px;color:#7B8794;text-transform:uppercase;letter-spacing:1px;margin-top:2px;">{month}</div>
            </td></tr>
            <tr><td style="padding:6px 4px;text-align:center;">{icon}</td></tr>
            <tr><td style="padding:0 4px 6px 4px;text-align:center;font-size:11px;color:#3E4C59;line-height:1.3;min-height:28px;">
              {label}
            </td></tr>
            <tr><td style="padding:4px 4px 4px 4px;text-align:center;">
              <div style="font-size:16px;font-weight:700;color:#C7372F;line-height:1.1;">{hi_f}&deg;</div>
              <div style="font-size:10px;color:#9AA5B1;line-height:1;">{hi_c}&deg;C</div>
              <div style="height:1px;background:#EDF0F3;margin:6px 10px;"></div>
              <div style="font-size:16px;font-weight:700;color:#2D9CDB;line-height:1.1;">{lo_f}&deg;</div>
              <div style="font-size:10px;color:#9AA5B1;line-height:1;">{lo_c}&deg;C</div>
            </td></tr>
            <tr><td style="padding:8px 4px 12px 4px;text-align:center;">
              <div style="font-size:12px;font-weight:600;color:#3E4C59;line-height:1;">{wind}</div>
              <div style="font-size:9px;color:#9AA5B1;letter-spacing:0.5px;text-transform:uppercase;margin-top:2px;">mph wind</div>
            </td></tr>
          </table>
        </td>""")

    gen_fmt = ("%A, %b %-d %Y at %-I:%M %p %Z" if sys.platform != "win32"
               else "%A, %b %#d %Y at %#I:%M %p %Z")
    generated = datetime.now(LOCAL_TZ).strftime(gen_fmt)

    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#F5F7FA;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F5F7FA;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="760" cellpadding="0" cellspacing="0" style="max-width:760px;background:#FFFFFF;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
        <tr><td style="padding:24px 24px 12px 24px;">
          <div style="font-size:13px;color:#7B8794;letter-spacing:0.5px;text-transform:uppercase;">7-Day Forecast</div>
          <div style="font-size:24px;font-weight:700;color:#1F2933;margin-top:4px;">{LOCATION_NAME}</div>
          <div style="font-size:12px;color:#9AA5B1;margin-top:4px;">Generated {generated}</div>
        </td></tr>
        <tr><td style="padding:8px 12px 20px 12px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            <tr>{''.join(cells)}</tr>
          </table>
        </td></tr>
        <tr><td style="padding:12px 24px 24px 24px;font-size:11px;color:#9AA5B1;text-align:center;border-top:1px solid #EDF0F3;">
          Data: <a href="https://open-meteo.com" style="color:#9AA5B1;">Open-Meteo</a> &middot; Times in America/Los_Angeles
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


# --- Send -------------------------------------------------------------------

def send_email(html: str, *, sender: str, recipient: str, password: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"Weekly Forecast — {LOCATION_NAME}"
    msg["From"] = sender
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content("Your email client does not support HTML. Open in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.starttls()
        s.login(sender, password)
        s.send_message(msg)


# --- Time guard -------------------------------------------------------------

def is_target_time() -> bool:
    """True if 'now' is Sunday 8-10pm Pacific. Used to gate the dual-cron."""
    now = datetime.now(LOCAL_TZ)
    return now.weekday() == 6 and 20 <= now.hour <= 22  # Sunday, 8-10pm


# --- Main -------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Write preview.html, do not send")
    ap.add_argument("--force", action="store_true", help="Skip the time-of-day guard")
    args = ap.parse_args()

    if not args.dry_run and not args.force and not is_target_time():
        now = datetime.now(LOCAL_TZ)
        print(f"Skip: not Sun 8-10pm Pacific (now: {now:%a %H:%M %Z}). Use --force to override.")
        return 0

    print("Fetching forecast from Open-Meteo...")
    data = fetch_forecast()
    html = render_html(data)

    if args.dry_run:
        with open("preview.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Wrote preview.html")
        return 0

    sender    = os.environ.get("SMTP_USER", "dhrumil84@gmail.com")
    password  = os.environ.get("SMTP_PASSWORD")
    recipient = os.environ.get("RECIPIENT_EMAIL", "patel.dhrumil@protonmail.com")
    if not password:
        print("ERROR: SMTP_PASSWORD env var not set.", file=sys.stderr)
        return 1

    print(f"Sending to {recipient}...")
    send_email(html, sender=sender, recipient=recipient, password=password)
    print("Sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
