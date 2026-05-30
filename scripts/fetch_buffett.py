"""Fetch Berkshire Hathaway annual letters from berkshirehathaway.com.

Run:   python scripts/fetch_buffett.py [--refresh]
Output: corpus/buffett/<year>.txt

Strategy:
  - HTML letters (~1977-1997): parse with BeautifulSoup, DROP every <table>
    element (financial tables) before extracting text.
  - PDF letters (~1998-present): pdfplumber for text extraction, then mask
    out detected table regions, then apply a numeric-line filter as a
    second pass for safety.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import time
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

from scripts._clean import drop_tabular_lines, normalize_text

BASE = "https://www.berkshirehathaway.com/letters/"
OUT_DIR = Path(__file__).resolve().parent.parent / "corpus" / "buffett"
SLEEP = 0.5

# The letters.html index is behind a Sucuri WAF that blocks scripted requests,
# but the actual letter files are not firewalled. Hit each year directly using
# the historical naming convention.
def _candidate_urls(year: int) -> list[str]:
    """Patterns to try in priority order. First 200 OK with a real body wins."""
    if year <= 1997:
        return [BASE + f"{year}.html"]
    if year <= 2006:
        # 1998-2006 .html pages are stubs that redirect to PDFs. Hit PDF directly.
        return [BASE + f"{year}pdf.pdf", BASE + f"{year}ltr.pdf", BASE + f"{year}htm.html"]
    return [BASE + f"{year}ltr.pdf"]

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Note: explicitly NOT advertising "br" — requests doesn't auto-decode
    # Brotli unless the `brotli` package is installed, and Berkshire's CDN
    # will pick br if we say we accept it.
    "Accept-Encoding": "gzip, deflate",
}


def discover_letters(start_year: int = 1977, end_year: int | None = None) -> dict[int, list[str]]:
    """Return {year: [candidate_urls]} for every year in range."""
    from datetime import date
    if end_year is None:
        end_year = date.today().year
    return {y: _candidate_urls(y) for y in range(start_year, end_year + 1)}


def clean_html_letter(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Drop all tables — these are financial summaries we don't want as prose
    for tab in soup.find_all("table"):
        tab.decompose()
    for tag in soup(["script", "style", "img"]):
        tag.decompose()
    text = soup.get_text("\n")
    # Buffett HTML letters often have a top header like "BERKSHIRE HATHAWAY INC." plus addresses
    text = re.sub(r"^[\s\S]*?To the Shareholders[^\n]*\n", "To the Shareholders\n", text, count=1)
    # Numeric-line safety net
    text = drop_tabular_lines(text)
    return normalize_text(text)


def clean_pdf_letter(pdf_bytes: bytes) -> str:
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            try:
                tables = page.find_tables()
                table_bboxes = [t.bbox for t in tables]
            except Exception:
                table_bboxes = []
            # Mask out table regions by cropping them out, then extract text from the rest
            try:
                if table_bboxes:
                    # Filter out characters within any table bbox
                    def not_in_tables(obj):
                        for x0, top, x1, bottom in table_bboxes:
                            if (obj["x0"] >= x0 and obj["x1"] <= x1
                                    and obj["top"] >= top and obj["bottom"] <= bottom):
                                return False
                        return True
                    filtered = page.filter(not_in_tables)
                    text = filtered.extract_text() or ""
                else:
                    text = page.extract_text() or ""
            except Exception:
                text = page.extract_text() or ""
            parts.append(text)
    text = "\n".join(parts)
    # Strip running headers like "BERKSHIRE HATHAWAY INC."
    text = re.sub(r"^BERKSHIRE HATHAWAY INC\.\s*$", "", text, flags=re.M)
    # Strip page numbers (lines that are just a number)
    text = re.sub(r"^\s*\d{1,3}\s*$", "", text, flags=re.M)
    # Numeric-line filter
    text = drop_tabular_lines(text)
    return normalize_text(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--only", help="Comma-separated years")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    sess.headers.update(BROWSER_HEADERS)

    links = discover_letters()
    print(f"[discover] will attempt {len(links)} years: {min(links)}-{max(links)}")

    if args.only:
        wanted = {int(y) for y in args.only.split(",")}
        links = {y: u for y, u in links.items() if y in wanted}

    totals: dict[int, int] = {}
    for year, candidates in links.items():
        out_path = OUT_DIR / f"{year}.txt"
        if out_path.exists() and not args.refresh:
            totals[year] = out_path.stat().st_size
            continue
        text = None
        used_url = None
        for url in candidates:
            try:
                resp = sess.get(url, timeout=60)
                if resp.status_code != 200 or len(resp.content) < 2000:
                    continue
                if url.lower().endswith(".pdf"):
                    text = clean_pdf_letter(resp.content)
                else:
                    text = clean_html_letter(resp.text)
                used_url = url
                break
            except Exception as e:
                print(f"  [warn {year}] {url} -> {e}", file=sys.stderr)
                continue
        if not text or len(text) < 1000:
            print(f"  [skip {year}] no usable candidate (tried {len(candidates)})")
            continue
        print(f"[fetch] {year}  {used_url}  -> {len(text):,} chars")
        out_path.write_text(text, encoding="utf-8")
        totals[year] = len(text)
        time.sleep(SLEEP)

    print(f"\n=== Summary ===")
    for y, sz in sorted(totals.items()):
        print(f"  {y}: {sz:>10,} chars")
    print(f"  TOTAL: {sum(totals.values()):,} chars across {len(totals)} letters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
