"""Fetch curated Gutenberg essays + the Federalist Papers.

Run:   python scripts/fetch_gutenberg.py [--refresh]
Output: corpus/gutenberg/<slug>.txt and corpus/federalist/federalist_papers.txt
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests

from scripts._clean import normalize_text, strip_gutenberg_chrome

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
GUTEN_DIR = CORPUS / "gutenberg"
FED_DIR = CORPUS / "federalist"
SLEEP = 0.5

# (gutenberg_id, slug, group). group: "gutenberg" or "federalist"
WORKS = [
    (5827,  "russell_problems_of_philosophy", "gutenberg"),
    (5116,  "james_pragmatism",               "gutenberg"),
    (26659, "james_will_to_believe",          "gutenberg"),
    (470,   "chesterton_heretics",            "gutenberg"),
    (130,   "chesterton_orthodoxy",           "gutenberg"),
    # NOTE: Mencken's Prejudices isn't on Project Gutenberg under a verified ID.
    # Skipping rather than fetching the wrong text. Add a known-good Mencken text
    # here later if you find one (try the Gutenberg search).
    (2944,  "emerson_essays_first_series",    "gutenberg"),
    (2945,  "emerson_essays_second_series",   "gutenberg"),
    (205,   "thoreau_walden",                 "gutenberg"),
    (71,    "thoreau_civil_disobedience",     "gutenberg"),
    (1404,  "federalist_papers",              "federalist"),
]

# Try these URL patterns in order; Gutenberg is inconsistent across older/newer texts
URL_PATTERNS = [
    "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt",
    "https://www.gutenberg.org/files/{id}/{id}-0.txt",
    "https://www.gutenberg.org/files/{id}/{id}.txt",
    "https://www.gutenberg.org/ebooks/{id}.txt.utf-8",
]


def strip_toc(text: str) -> str:
    """Best-effort: drop a Table of Contents block if present near the top.

    Heuristic: scan the first 200 lines for a block of short lines (most <60 chars)
    framed by a 'Contents' header. Drop everything from the header to the end of
    that block.
    """
    lines = text.splitlines()
    look = lines[:300]
    for i, line in enumerate(look):
        if re.match(r"^\s*(?:CONTENTS|Contents|TABLE OF CONTENTS)\s*$", line):
            # Skip ahead while lines remain mostly short / titled
            j = i + 1
            short_run = 0
            while j < len(lines) and short_run < 80:
                ln = lines[j].strip()
                if not ln:
                    short_run += 1
                elif len(ln) < 80 and not ln.endswith("."):
                    short_run = 0
                else:
                    break
                j += 1
            return "\n".join(lines[:i] + lines[j:])
    return text


def fetch_text(sess: requests.Session, book_id: int) -> str | None:
    for pat in URL_PATTERNS:
        url = pat.format(id=book_id)
        try:
            r = sess.get(url, timeout=30)
            if r.status_code == 200 and len(r.text) > 5000:
                return r.text
        except Exception:
            continue
    return None


def clean(raw: str) -> str:
    text = strip_gutenberg_chrome(raw)
    text = strip_toc(text)
    return normalize_text(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    GUTEN_DIR.mkdir(parents=True, exist_ok=True)
    FED_DIR.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    sess.headers.update({"User-Agent": "weekly-update-corpus/1.0 (personal)"})

    totals = {}
    for book_id, slug, group in WORKS:
        out_dir = GUTEN_DIR if group == "gutenberg" else FED_DIR
        out_path = out_dir / f"{slug}.txt"
        if out_path.exists() and not args.refresh:
            totals[slug] = out_path.stat().st_size
            continue
        print(f"[fetch] {slug} (Gutenberg #{book_id})", flush=True)
        raw = fetch_text(sess, book_id)
        if raw is None:
            print(f"  ERROR: could not fetch from any URL pattern", file=sys.stderr)
            continue
        cleaned = clean(raw)
        out_path.write_text(cleaned, encoding="utf-8")
        totals[slug] = len(cleaned)
        print(f"  -> {len(cleaned):,} chars")
        time.sleep(SLEEP)

    print(f"\n=== Summary ===")
    for slug, sz in totals.items():
        print(f"  {slug:40s} {sz:>10,} chars")
    print(f"  TOTAL: {sum(totals.values()):,} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
