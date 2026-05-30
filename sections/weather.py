"""7-day forecast section for Anaheim, CA. Data from Open-Meteo (no API key)."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime

from sections._common import LOCAL_TZ, section_card

LATITUDE = 33.8366
LONGITUDE = -117.9143
LOCATION_NAME = "Anaheim, CA"

# WMO 4677 weather code -> (label, emoji). Emoji because inline SVG is stripped
# by ProtonMail and remote images get blocked by default; emoji renders natively.
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
DEFAULT_ICON = "☁️"


def _fetch() -> dict:
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
        return json.loads(resp.read().decode("utf-8"))


def _f_to_c(f: float) -> int:
    return round((f - 32) * 5 / 9)


def render() -> str:
    """Return the weather section as a self-contained HTML card."""
    data = _fetch()
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
        dow = d.strftime("%a").upper()
        date_num = d.strftime(day_fmt)
        month = d.strftime("%b")
        is_today = (i == 0)

        label, icon = WMO.get(codes[i], ("—", DEFAULT_ICON))
        hi_f = round(highs[i]); hi_c = _f_to_c(highs[i])
        lo_f = round(lows[i]);  lo_c = _f_to_c(lows[i])
        wind = round(winds[i])

        bg     = "#FFF8E1" if is_today else "#FFFFFF"
        accent = "#F6B100" if is_today else "transparent"

        cells.append(f"""
        <td valign="top" width="14.28%" style="padding:0 4px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{bg};border-radius:10px;border-top:3px solid {accent};">
            <tr><td style="padding:12px 6px 4px 6px;text-align:center;">
              <div style="font-size:18px;font-weight:800;color:#1F2933;letter-spacing:1.5px;line-height:1;">{dow}</div>
              <div style="font-size:22px;font-weight:700;color:#1F2933;line-height:1.1;margin-top:6px;">{date_num}</div>
              <div style="font-size:11px;color:#7B8794;text-transform:uppercase;letter-spacing:1px;margin-top:2px;">{month}</div>
            </td></tr>
            <tr><td style="padding:6px 4px;text-align:center;font-size:40px;line-height:1;">{icon}</td></tr>
            <tr><td style="padding:0 4px 6px 4px;text-align:center;font-size:11px;color:#3E4C59;line-height:1.3;min-height:28px;">{label}</td></tr>
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

    body = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr>{''.join(cells)}</tr>
    </table>"""
    return section_card("7-Day Forecast", LOCATION_NAME, body, body_padding="12px 12px 20px 12px")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    html = render()
    if args.dry_run:
        print(html)
    else:
        print("Use update.py to send. Section preview:")
        print(html[:400] + "...")
