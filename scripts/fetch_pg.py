"""Fetch Paul Graham essays from paulgraham.com.

Run:   python scripts/fetch_pg.py [--limit N] [--refresh]
Output: corpus/pg/<slug>.txt
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from scripts._clean import normalize_text

BASE = "http://www.paulgraham.com/"
INDEX = BASE + "articles.html"
OUT_DIR = Path(__file__).resolve().parent.parent / "corpus" / "pg"
SLEEP = 0.4

# Skip these — not essays
SKIP = {
    "index.html", "articles.html", "rss.html", "bio.html", "raq.html",
    "kedrosky.html", "lib.html", "spam.html", "rootsoflisp.html",
    "noop.html", "fix.html", "lwba.html", "rss-essays.html",
}

# Header / footer boilerplate to strip
HEADER_PATTERNS = [
    r"^\s*Want to start a startup\?[^\n]*\n",
    r"^\s*New:\s+[^\n]*\n",
]
# A multi-line "Get funded by Y Combinator." block appears at the top of every
# essay. Match across the line breaks PG inserts.
YC_BLOCK = re.compile(r"Get funded by\s*\n*\s*Y Combinator\s*\.\s*", re.I)

def find_essay_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("http") or href.startswith("#") or href.startswith("mailto:"):
            continue
        if not href.endswith(".html"):
            continue
        if href in SKIP or href in seen:
            continue
        seen.add(href)
        out.append(href)
    return out


def clean_pg(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove images, scripts, styles
    for tag in soup(["script", "style", "img"]):
        tag.decompose()
    # PG's essays use <br> for line breaks within paragraphs and blank lines between
    text = soup.get_text("\n")

    # Strip well-known header lines
    for pat in HEADER_PATTERNS:
        text = re.sub(pat, "", text, flags=re.M)
    text = YC_BLOCK.sub("", text)

    # Strip "Notes" / "Notes:" footer and everything after
    text = re.split(r"\n\s*Notes?\s*\n", text, maxsplit=1)[0]

    # Strip "Thanks to ... for reading drafts" sentences
    text = re.sub(r"Thanks to [^.]{0,400}?(?:reading\s+(?:drafts|this)|comments)[^.]{0,100}\.", "", text, flags=re.S)

    # Strip "Related:" link blocks
    text = re.sub(r"\nRelated:[\s\S]*$", "", text)

    # Strip footnote markers [1], [2], ...
    text = re.sub(r"\[\d{1,3}\]", "", text)

    # If the content has a hard nav block at top (links), it'll usually be short tokens
    # separated by | — drop any line that's mostly that
    text = re.sub(r"^\s*\|[\s\S]+?\|\s*$", "", text, flags=re.M)

    return normalize_text(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="Cap number of essays")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    sess.headers.update({"User-Agent": "weekly-update-corpus/1.0 (personal)"})

    print(f"[index] {INDEX}")
    r = sess.get(INDEX, timeout=30)
    r.raise_for_status()
    links = find_essay_links(r.text)
    print(f"  found {len(links)} essay links")

    if args.limit:
        links = links[: args.limit]

    fetched = 0
    skipped = 0
    too_short = 0
    for href in links:
        slug = href.replace(".html", "")
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", slug)
        out_path = OUT_DIR / f"{slug}.txt"
        if out_path.exists() and not args.refresh:
            skipped += 1
            continue
        url = BASE + href
        try:
            resp = sess.get(url, timeout=30)
            if resp.status_code != 200:
                print(f"  [skip {resp.status_code}] {href}")
                continue
            text = clean_pg(resp.text)
            if len(text) < 500:
                too_short += 1
                continue
            out_path.write_text(text, encoding="utf-8")
            fetched += 1
            if fetched % 25 == 0:
                print(f"  ...{fetched} fetched")
        except Exception as e:
            print(f"  ERROR {href}: {e}", file=sys.stderr)
        time.sleep(SLEEP)

    print(f"\n=== Summary ===")
    print(f"  fetched: {fetched}, skipped (already had): {skipped}, too-short (dropped): {too_short}")
    total_chars = sum(p.stat().st_size for p in OUT_DIR.glob("*.txt"))
    print(f"  corpus total: {total_chars:,} chars across {len(list(OUT_DIR.glob('*.txt')))} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
