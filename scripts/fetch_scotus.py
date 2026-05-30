"""Fetch SCOTUS dissents + concurrences per justice from CourtListener.

Run:   python scripts/fetch_scotus.py [--limit N] [--refresh]
Output: corpus/scotus/<justice>.txt   (one file per justice, opinions concatenated)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from scripts._clean import normalize_text

API_OPINIONS = "https://www.courtlistener.com/api/rest/v4/opinions/"
API_PEOPLE   = "https://www.courtlistener.com/api/rest/v4/people/"
API = API_OPINIONS  # back-compat alias
# CourtListener requires a free API token for v4 endpoints.
# Get one at https://www.courtlistener.com/help/api/rest/#authentication
# (sign up, then visit your profile page; token shown there).
# Put it in a .env style export: COURTLISTENER_TOKEN=...
TOKEN_ENV = "COURTLISTENER_TOKEN"
# Their rate limiter trips much faster than the per-hour quota suggests.
# 2s between requests + a long backoff on 429 stays comfortably under it.
RETRY_429_WAIT = 300.0   # 5 min default; overridden by Retry-After header if present
MAX_429_RETRIES = 6
OUT_DIR = Path(__file__).resolve().parent.parent / "corpus" / "scotus"
PER_JUSTICE = 20         # target per justice (some may have fewer matches)
DATE_FROM = "2005-01-01"
# Valid opinion type codes (035concurrence_in_part isn't a real enum member;
# "in part" opinions are filed under the main 030/040 types).
OPINION_TYPES = ["030concurrence", "040dissent"]
SLEEP = 2.0

# (last_name, courtlistener_person_id). Hardcoded after verifying each by
# directly hitting /people/<id>/ — disambiguation via name lookup is too
# fragile (thousands of federal judges share these surnames).
JUSTICES: list[tuple[str, int]] = [
    ("Roberts",   2738),
    ("Thomas",    3200),
    ("Alito",     77),
    ("Sotomayor", 3045),
    ("Kagan",     1691),
    ("Gorsuch",   1250),
    ("Kavanaugh", 1713),
    ("Barrett",   8543),
    ("Jackson",   1609),
    ("Breyer",    384),
    ("Ginsburg",  1213),
    ("Scalia",    2852),
    ("Kennedy",   1747),
    ("Souter",    3046),
    ("Stevens",   3104),
]


def clean_scotus(text: str) -> str:
    """Strip case captions, syllabi, citations, footnote markers."""
    if not text:
        return ""

    # Trim everything before the first "JUSTICE X, [dissenting|concurring]..."
    m = re.search(
        r"JUSTICE\s+[A-Z][A-Za-z]+(?:[^.]{0,200}?)(?:dissenting|concurring)",
        text,
    )
    if m:
        text = text[m.start():]

    # Strip citation patterns
    text = re.sub(r"\b\d{1,3}\s+U\.\s*S\.\s+\d+(?:[-,–]\s*\d+)?", "", text)
    text = re.sub(r"\b\d{1,3}\s+S\.\s*Ct\.\s+\d+", "", text)
    text = re.sub(r"\b\d{1,3}\s+L\.\s*Ed\.\s*2d\s+\d+", "", text)
    text = re.sub(r"_+\s*U\.\s*S\.\s*_+", "", text)
    text = re.sub(r"slip\s+op\.,?\s+at\s+\d+", "", text, flags=re.I)
    text = re.sub(r"\bNo\.\s+\d{2}-\d+", "", text)

    # Strip parenthetical citation phrases
    text = re.sub(r"\(\s*citing[^)]+\)", "", text, flags=re.I)
    text = re.sub(r"\(\s*quoting[^)]+\)", "", text, flags=re.I)
    text = re.sub(r"\(\s*internal\s+quotation\s+marks?\s+omitted\s*\)", "", text, flags=re.I)
    text = re.sub(r"\(\s*alteration[s]?\s+in\s+original\s*\)", "", text, flags=re.I)
    text = re.sub(r"\(\s*emphasis\s+(?:added|omitted)\s*\)", "", text, flags=re.I)

    # Statute references
    text = re.sub(r"§+\s*\d+[\w\-]*(?:\([^)]+\))?", "", text)
    text = re.sub(r"\bPub\.\s*L\.\s*No\.\s*\d+[-\d]+", "", text)

    # Footnote markers (bracketed numbers)
    text = re.sub(r"\[\d{1,3}\]", "", text)
    # Sometimes footnotes appear as "n. 3" or "fn. 3"
    text = re.sub(r"\bn\.\s*\d{1,3}\b", "", text)

    # Empty parens/brackets left over
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\[\s*\]", "", text)

    # Stray comma sequences left by removals
    text = re.sub(r",\s*,\s*", ", ", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r"\s+\.", ".", text)

    return normalize_text(text)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["sup", "script", "style"]):
        tag.decompose()
    return soup.get_text("\n")


def get_with_backoff(sess: requests.Session, url: str, params: dict) -> requests.Response | None:
    """GET with retry on 429 and verbose error on 4xx."""
    for attempt in range(MAX_429_RETRIES + 1):
        r = sess.get(url, params=params, timeout=30)
        if r.status_code == 429:
            # CourtListener usually sends Retry-After in seconds. Honor it but cap to 1 hour.
            wait = RETRY_429_WAIT
            ra = r.headers.get("Retry-After")
            if ra and ra.isdigit():
                wait = min(int(ra), 3600)
            print(f"    [429] rate-limited, sleeping {wait:.0f}s (attempt {attempt+1}/{MAX_429_RETRIES+1})", flush=True)
            time.sleep(wait)
            continue
        if 400 <= r.status_code < 500:
            print(f"    [{r.status_code}] {r.text[:500]}", file=sys.stderr)
            return None
        r.raise_for_status()
        return r
    print(f"    [429] giving up after {MAX_429_RETRIES} retries", file=sys.stderr)
    return None


def fetch_one_justice(session: requests.Session, last_name: str, person_id: int, limit: int) -> list[str]:
    """Return list of cleaned opinion texts for this justice across all opinion types."""

    seen_ids: set[int] = set()
    out: list[str] = []

    for op_type in OPINION_TYPES:
        if len(out) >= limit:
            break
        params = {
            "cluster__docket__court": "scotus",
            "type": op_type,
            "author": person_id,
            "page_size": 50,
        }
        r = get_with_backoff(session, API_OPINIONS, params)
        if r is None:
            continue
        results = r.json().get("results", [])
        time.sleep(SLEEP)

        for op in results:
            if op.get("id") in seen_ids:
                continue
            seen_ids.add(op.get("id"))
            # Optional date filter, client-side
            cluster = op.get("cluster")
            if isinstance(cluster, dict):
                date_filed = cluster.get("date_filed", "")
                if date_filed and date_filed < DATE_FROM:
                    continue
            raw = op.get("plain_text") or html_to_text(op.get("html_with_citations") or op.get("html") or "")
            cleaned = clean_scotus(raw)
            if len(cleaned) < 500:
                continue
            out.append(cleaned)
            if len(out) >= limit:
                break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=PER_JUSTICE, help=f"Per-justice cap (default {PER_JUSTICE})")
    ap.add_argument("--refresh", action="store_true", help="Re-fetch even if file exists")
    ap.add_argument("--only", help="Comma-separated justice surnames to fetch")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    token = os.environ.get(TOKEN_ENV)
    if not token:
        print(f"ERROR: set {TOKEN_ENV} env var. Get a free token at", file=sys.stderr)
        print("  https://www.courtlistener.com/help/api/rest/#authentication", file=sys.stderr)
        return 1
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "weekly-update-corpus/1.0 (personal)",
        "Authorization": f"Token {token}",
    })

    only_set = set(args.only.split(",")) if args.only else None
    targets = [(last, pid) for last, pid in JUSTICES if not only_set or last in only_set]
    totals = {}
    for last, person_id in targets:
        out_path = OUT_DIR / f"{last.lower()}.txt"
        if out_path.exists() and not args.refresh:
            print(f"[skip] {last}: file exists ({out_path.stat().st_size:,} bytes). Use --refresh to redo.")
            totals[last] = out_path.stat().st_size
            continue
        print(f"[fetch] {last} (id={person_id})...", flush=True)
        try:
            opinions = fetch_one_justice(sess, last, person_id, args.limit)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            continue
        if not opinions:
            print(f"  WARN: no opinions found for {last}")
            continue
        body = ("\n\n" + "=" * 60 + "\n\n").join(opinions)
        out_path.write_text(body, encoding="utf-8")
        totals[last] = len(body)
        print(f"  -> {len(opinions)} opinions, {len(body):,} chars")
        time.sleep(SLEEP)

    print("\n=== Summary ===")
    for j, sz in totals.items():
        print(f"  {j:12s} {sz:>10,} chars")
    print(f"  TOTAL        {sum(totals.values()):>10,} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
