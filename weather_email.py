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

# --- WMO weather code -> (label, emoji icon) --------------------------------
# Codes per https://open-meteo.com/en/docs (WMO 4677).
# Emoji because inline SVG is stripped by ProtonMail and several other clients,
# and remote/base64 images get blocked by default. Emoji render natively and
# work in 100% of mail clients.

WMO = {
    0:  ("Clear",              "☀️"),       # ☀️
    1:  ("Mostly Clear",       "\U0001F324️"),   # 🌤️
    2:  ("Partly Cloudy",      "⛅"),             # ⛅
    3:  ("Cloudy",             "☁️"),       # ☁️
    45: ("Fog",                "\U0001F32B️"),   # 🌫️
    48: ("Freezing Fog",       "\U0001F32B️"),
    51: ("Light Drizzle",      "\U0001F326️"),   # 🌦️
    53: ("Drizzle",            "\U0001F326️"),
    55: ("Heavy Drizzle",      "\U0001F327️"),   # 🌧️
    56: ("Freezing Drizzle",   "\U0001F327️"),
    57: ("Freezing Drizzle",   "\U0001F327️"),
    61: ("Light Rain",         "\U0001F326️"),
    63: ("Rain",               "\U0001F327️"),
    65: ("Heavy Rain",         "\U0001F327️"),
    66: ("Freezing Rain",      "\U0001F327️"),
    67: ("Freezing Rain",      "\U0001F327️"),
    71: ("Light Snow",         "\U0001F328️"),   # 🌨️
    73: ("Snow",               "\U0001F328️"),
    75: ("Heavy Snow",         "❄️"),       # ❄️
    77: ("Snow Grains",        "\U0001F328️"),
    80: ("Rain Showers",       "\U0001F326️"),
    81: ("Rain Showers",       "\U0001F327️"),
    82: ("Heavy Rain Showers", "\U0001F327️"),
    85: ("Snow Showers",       "\U0001F328️"),
    86: ("Heavy Snow Showers", "❄️"),
    95: ("Thunderstorm",       "⛈️"),       # ⛈️
    96: ("Thunderstorm + Hail","⛈️"),
    99: ("Severe Thunderstorm","⛈️"),
}
DEFAULT_ICON = "☁️"  # ☁️

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

        label, icon = WMO.get(codes[i], ("—", DEFAULT_ICON))
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
            <tr><td style="padding:6px 4px;text-align:center;font-size:40px;line-height:1;">{icon}</td></tr>
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
        <tr><td style="padding:28px 24px 8px 24px;text-align:center;border-bottom:1px solid #EDF0F3;">
          <div style="font-size:28px;font-weight:800;color:#1F2933;letter-spacing:-0.5px;">Patel Family Weekly Update</div>
          <div style="font-size:12px;color:#9AA5B1;margin-top:6px;">{generated}</div>
        </td></tr>
        <tr><td style="padding:24px 24px 4px 24px;">
          <div style="font-size:12px;color:#7B8794;letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">7-Day Forecast</div>
          <div style="font-size:18px;font-weight:600;color:#1F2933;margin-top:2px;">{LOCATION_NAME}</div>
        </td></tr>
        <tr><td style="padding:12px 12px 20px 12px;">
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
    msg["Subject"] = "Patel Family Weekly Update"
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
