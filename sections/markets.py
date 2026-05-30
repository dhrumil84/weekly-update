"""Market indices section: prior-week, MTD, YTD returns.

Data from Yahoo Finance via yfinance. Sunday timing means Friday close is the
most recent print, so no intraday concerns.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import yfinance as yf

from sections._common import section_card, section_error

# (ticker, display name, optional subtitle)
INDICES = [
    ("^GSPC", "S&P 500",          ""),
    ("^IXIC", "Nasdaq Composite", ""),
    ("^RUI",  "Russell 1000",     "large-cap"),
    ("^RUT",  "Russell 2000",     "small-cap"),
    ("^RUA",  "Russell 3000",     "total market"),
]

POS = "#27AE60"
NEG = "#C7372F"
ZERO = "#7B8794"


def _pct_color(p: float) -> str:
    if p > 0.0005: return POS
    if p < -0.0005: return NEG
    return ZERO


def _fmt_pct(p: float) -> str:
    sign = "+" if p >= 0 else "−"  # unicode minus for nice alignment
    return f"{sign}{abs(p)*100:.2f}%"


def _fmt_price(x: float) -> str:
    return f"{x:,.2f}"


def _returns_for(ticker: str) -> dict:
    """Return dict with latest close, prior_week, mtd, ytd as decimals."""
    # 14 months gives us comfortable headroom for YTD + prior year-end close.
    hist = yf.Ticker(ticker).history(period="14mo", auto_adjust=False)
    if hist.empty:
        raise RuntimeError(f"No data returned for {ticker}")
    closes = hist["Close"].dropna()
    last_dt = closes.index[-1].date()
    last = float(closes.iloc[-1])

    # Prior week: last 5 trading days (handles holidays automatically).
    if len(closes) < 6:
        raise RuntimeError(f"Not enough history for {ticker}")
    prior_week_base = float(closes.iloc[-6])
    pw = last / prior_week_base - 1

    # MTD: last close of previous month.
    this_month = last_dt.replace(day=1)
    prev_month_closes = closes[closes.index.date < this_month]
    if prev_month_closes.empty:
        mtd = 0.0
    else:
        mtd = last / float(prev_month_closes.iloc[-1]) - 1

    # YTD: last close of previous calendar year.
    this_year_start = date(last_dt.year, 1, 1)
    prev_year_closes = closes[closes.index.date < this_year_start]
    if prev_year_closes.empty:
        ytd = 0.0
    else:
        ytd = last / float(prev_year_closes.iloc[-1]) - 1

    return {"last": last, "as_of": last_dt, "pw": pw, "mtd": mtd, "ytd": ytd}


def _row(name: str, subtitle: str, r: dict) -> str:
    def cell(p: float) -> str:
        return f"""<td align="right" style="padding:12px 10px;border-bottom:1px solid #EDF0F3;
            font-family:'SF Mono',Consolas,Menlo,monospace;font-size:14px;font-weight:600;
            color:{_pct_color(p)};white-space:nowrap;">{_fmt_pct(p)}</td>"""
    sub_html = (f'<span style="font-size:11px;font-weight:400;color:#9AA5B1;margin-left:6px;">'
                f'({subtitle})</span>') if subtitle else ""
    return f"""
    <tr>
      <td style="padding:12px 10px;border-bottom:1px solid #EDF0F3;font-size:14px;font-weight:600;color:#1F2933;">{name}{sub_html}</td>
      <td align="right" style="padding:12px 10px;border-bottom:1px solid #EDF0F3;
          font-family:'SF Mono',Consolas,Menlo,monospace;font-size:13px;color:#3E4C59;white-space:nowrap;">{_fmt_price(r['last'])}</td>
      {cell(r['pw'])}
      {cell(r['mtd'])}
      {cell(r['ytd'])}
    </tr>"""


def render() -> str:
    try:
        results = [(name, sub, _returns_for(t)) for t, name, sub in INDICES]
    except Exception as e:
        return section_error("Markets", "Weekly Recap", str(e))

    as_of = max(r["as_of"] for _, _, r in results)
    sub = f"As of {as_of:%a, %b %d %Y} close"

    header = """
    <tr>
      <th align="left"  style="padding:8px 10px;font-size:11px;color:#7B8794;text-transform:uppercase;letter-spacing:1px;border-bottom:2px solid #EDF0F3;">Index</th>
      <th align="right" style="padding:8px 10px;font-size:11px;color:#7B8794;text-transform:uppercase;letter-spacing:1px;border-bottom:2px solid #EDF0F3;">Last</th>
      <th align="right" style="padding:8px 10px;font-size:11px;color:#7B8794;text-transform:uppercase;letter-spacing:1px;border-bottom:2px solid #EDF0F3;">Week</th>
      <th align="right" style="padding:8px 10px;font-size:11px;color:#7B8794;text-transform:uppercase;letter-spacing:1px;border-bottom:2px solid #EDF0F3;">MTD</th>
      <th align="right" style="padding:8px 10px;font-size:11px;color:#7B8794;text-transform:uppercase;letter-spacing:1px;border-bottom:2px solid #EDF0F3;">YTD</th>
    </tr>"""
    rows = "".join(_row(name, sub, r) for name, sub, r in results)
    body = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      {header}{rows}
    </table>"""
    return section_card("Markets", sub, body)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(render())
