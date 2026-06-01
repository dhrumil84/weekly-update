"""Pull a Standard Ebooks book as plain text (no tooling beyond Python deps).

Standard Ebooks publishes a single-page HTML view of every book. We grab that,
strip HTML and footnotes, and write to corpus/custom/<slug>.txt.

Usage:
  python -m scripts.fetch_standardebooks <url-or-slug>

  # By full book URL:
  python -m scripts.fetch_standardebooks \\
    https://standardebooks.org/ebooks/bertrand-russell/roads-to-freedom

  # By slug (shorthand):
  python -m scripts.fetch_standardebooks bertrand-russell/roads-to-freedom

You can pass multiple at once.
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

OUT_DIR = Path(__file__).resolve().parent.parent / "corpus" / "custom"
BASE = "https://standardebooks.org"
SLEEP = 0.5


def _normalize_input(arg: str) -> str:
    """Accept either a full URL or 'author/title' slug. Return the single-page URL."""
    if arg.startswith("http"):
        # Strip trailing slash and possible /text/single-page suffix
        url = arg.rstrip("/")
        if url.endswith("/text/single-page"):
            return url
        return url + "/text/single-page"
    slug = arg.strip("/")
    return f"{BASE}/ebooks/{slug}/text/single-page"


def _slug_from_url(url: str) -> str:
    """Turn .../ebooks/author/title/text/single-page into author_title."""
    m = re.search(r"/ebooks/([^/]+)/([^/]+)/", url)
    if not m:
        return "unknown"
    return f"{m.group(1).replace('-', '_')}__{m.group(2).replace('-', '_')}"


def clean(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Drop scripts, styles, the SE colophon, and any footnote refs
    for tag in soup(["script", "style", "img", "header", "nav"]):
        tag.decompose()
    # Standard Ebooks marks endnote refs with <a href="#endnote-N" ...>
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("#"):
            a.decompose()
    # Strip endnotes section at the bottom (id="endnotes")
    endnotes = soup.find(id="endnotes")
    if endnotes:
        endnotes.decompose()
    # Strip the colophon (about the edition) and imprint (license)
    for sec_id in ("colophon", "imprint", "uncopyright", "halftitlepage", "titlepage"):
        sec = soup.find(id=sec_id)
        if sec:
            sec.decompose()
    text = soup.get_text("\n")
    return normalize_text(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="+",
                    help="Book URLs or 'author/title' slugs")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
    })

    for target in args.targets:
        url = _normalize_input(target)
        slug = _slug_from_url(url)
        out_path = OUT_DIR / f"{slug}.txt"
        if out_path.exists() and not args.refresh:
            print(f"[skip] {slug}: file exists ({out_path.stat().st_size:,} bytes). --refresh to redo.")
            continue
        print(f"[fetch] {url}", flush=True)
        try:
            r = sess.get(url, timeout=60)
            r.raise_for_status()
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            continue
        text = clean(r.text)
        if len(text) < 1000:
            print(f"  WARN: very short ({len(text)} chars), skipping")
            continue
        out_path.write_text(text, encoding="utf-8")
        print(f"  -> corpus/custom/{slug}.txt  ({len(text):,} chars)")
        time.sleep(SLEEP)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
