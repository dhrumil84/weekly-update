"""Word of the day section.

Pulls a random substantive word from corpus/, looks up its definition via the
Free Dictionary API, and shows 3 example sentences drawn from the corpus
itself (attributed to source).

Deterministic per ISO-week so re-running the same Sunday yields the same word.
"""
from __future__ import annotations

import argparse
import html
import json
import random
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from functools import lru_cache
from pathlib import Path

from sections._common import LOCAL_TZ, section_card, section_error

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"
DICT_API = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"

MIN_WORD_LEN = 5
MIN_FREQUENCY = 2
MAX_DICT_LOOKUPS = 25     # how many candidates to try before giving up
NUM_EXAMPLES = 3
MIN_EXAMPLE_LEN = 40
MAX_EXAMPLE_LEN = 260

# Compact English stop-word list (hand-curated; no NLTK dep).
STOP_WORDS = frozenset("""
about above after again against alone along already also although always among
another any anyone anything anywhere are around because been before being below
between both came cannot could could does doing done down during each either
else enough even ever every everyone everything everywhere from further given
goes going gone good great hand have having here hers herself himself however
indeed inside instead into itself just keep kept know known last later least
less like little look made make many maybe might more most much must myself
near need never next none nothing once only other ought ours ourselves over
overall perhaps quite rather really same seem seemed seems shall should show
showed shown since some someone something sometimes somewhere soon still such
take taken than that their theirs them themselves then there these they thing
things think this those though through thus together took toward under unless
until upon used uses using usually very want wants were what when where which
while whose will with within without would yourself yourselves
""".split())


# ---- corpus loading -------------------------------------------------------

@lru_cache(maxsize=1)
def _load_corpus() -> dict[str, str]:
    """Return {posix_path: text} for every .txt file under corpus/."""
    out: dict[str, str] = {}
    if not CORPUS_DIR.exists():
        return out
    for p in CORPUS_DIR.rglob("*.txt"):
        if p.name.startswith("."):
            continue
        try:
            out[p.as_posix()] = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
    return out


WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z]+\b")  # no apostrophes/hyphens/digits


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


@lru_cache(maxsize=1)
def _candidate_words() -> list[str]:
    """Filter to substantive words. Cached per process."""
    counter: Counter[str] = Counter()
    for text in _load_corpus().values():
        counter.update(_tokenize(text))
    return [
        w for w, freq in counter.items()
        if len(w) >= MIN_WORD_LEN
        and freq >= MIN_FREQUENCY
        and w not in STOP_WORDS
    ]


# ---- dictionary API -------------------------------------------------------

def _lookup_definition(word: str) -> dict | None:
    """Hit Free Dictionary API. Returns the first entry dict, or None on 404/error."""
    url = DICT_API.format(word=urllib.parse.quote(word))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "weekly-update/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, list) and data:
            return data[0]
    except Exception:
        return None
    return None


# ---- example sentences from corpus ----------------------------------------

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")


def _find_examples(word: str, n: int, rng: random.Random) -> list[tuple[str, str]]:
    """Return up to n (sentence, source_path) tuples mentioning the word."""
    pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
    matches: list[tuple[str, str]] = []
    for path, text in _load_corpus().items():
        if not pattern.search(text):
            continue
        for sent in SENTENCE_SPLIT.split(text):
            if not pattern.search(sent):
                continue
            sent_clean = re.sub(r"\s+", " ", sent).strip()
            if MIN_EXAMPLE_LEN <= len(sent_clean) <= MAX_EXAMPLE_LEN:
                matches.append((sent_clean, path))
    rng.shuffle(matches)
    # Prefer one example per source so we don't show 3 sentences from the same file
    picked: list[tuple[str, str]] = []
    seen_sources: set[str] = set()
    for sent, path in matches:
        if path in seen_sources:
            continue
        picked.append((sent, path))
        seen_sources.add(path)
        if len(picked) == n:
            return picked
    # If we still don't have enough, allow repeats
    for sent, path in matches:
        if (sent, path) in [(s, p) for s, p in picked]:
            continue
        picked.append((sent, path))
        if len(picked) == n:
            break
    return picked


# ---- source labels --------------------------------------------------------

def _source_label(posix_path: str) -> str:
    """Turn a corpus path into a human-readable citation."""
    p = Path(posix_path)
    rel = p.relative_to(CORPUS_DIR)
    parts = rel.parts
    subdir = parts[0] if len(parts) > 1 else "custom"
    stem = p.stem

    if subdir == "scotus":
        return f"Justice {stem.title()}, SCOTUS opinion"
    if subdir == "pg":
        return f"Paul Graham, &ldquo;{stem.replace('_', ' ').title()}&rdquo;"
    if subdir == "buffett":
        return f"Buffett, {stem} shareholder letter"
    if subdir == "federalist":
        return "The Federalist Papers"
    if subdir == "gutenberg":
        # russell_problems_of_philosophy -> Russell, "Problems Of Philosophy"
        bits = stem.split("_", 1)
        if len(bits) == 2:
            author, title = bits
            return f"{author.title()}, &ldquo;{title.replace('_', ' ').title()}&rdquo;"
        return stem.replace("_", " ").title()
    if subdir == "custom":
        return stem.replace("_", " ").title()
    return stem


# ---- rendering ------------------------------------------------------------

def _highlight(sentence: str, word: str) -> str:
    """Bold the matched word in a sentence (HTML-escaped)."""
    escaped = html.escape(sentence)
    return re.sub(
        rf"\b({re.escape(word)})\b",
        r'<strong style="color:#1F2933;">\1</strong>',
        escaped,
        flags=re.IGNORECASE,
    )


def _pick_word_and_definition(rng: random.Random, candidates: list[str]) -> tuple[str, dict] | None:
    sample_size = min(len(candidates), MAX_DICT_LOOKUPS)
    for word in rng.sample(candidates, sample_size):
        defn = _lookup_definition(word)
        if defn and defn.get("meanings"):
            return word, defn
    return None


def render() -> str:
    try:
        candidates = _candidate_words()
        if not candidates:
            return section_error("Word of the Day", "—",
                                 "Corpus is empty or yielded no candidates. Run the fetcher scripts.")
        # Deterministic per ISO week
        from datetime import datetime
        today = datetime.now(LOCAL_TZ).date()
        iso_year, iso_week, _ = today.isocalendar()
        rng = random.Random(iso_year * 100 + iso_week)
        picked = _pick_word_and_definition(rng, candidates)
        if not picked:
            return section_error("Word of the Day", "—",
                                 "Dictionary API didn't find any of the sampled candidates.")
        word, definition = picked
        examples = _find_examples(word, NUM_EXAMPLES, rng)
    except Exception as e:
        return section_error("Word of the Day", "—", f"{type(e).__name__}: {e}")

    phonetic = (definition.get("phonetic") or "").strip()
    meanings = definition.get("meanings") or []

    # Build body: phonetic line, then up to 3 (POS + first definition), then examples
    parts: list[str] = []

    if phonetic:
        parts.append(
            f'<div style="font-size:14px;color:#7B8794;font-style:italic;margin:-4px 0 16px 0;">{html.escape(phonetic)}</div>'
        )

    for meaning in meanings[:3]:
        pos = (meaning.get("partOfSpeech") or "").strip()
        defs = meaning.get("definitions") or []
        if not defs:
            continue
        first_def = (defs[0].get("definition") or "").strip()
        parts.append(f"""
        <div style="margin-bottom:14px;">
          <div style="font-size:11px;color:#7B8794;text-transform:uppercase;letter-spacing:1.5px;font-weight:600;">{html.escape(pos)}</div>
          <div style="font-size:14px;color:#3E4C59;margin-top:4px;line-height:1.5;">{html.escape(first_def)}</div>
        </div>""")

    if examples:
        ex_html = []
        for sent, path in examples:
            hl = _highlight(sent, word)
            label = _source_label(path)
            ex_html.append(f"""
            <div style="margin-top:14px;">
              <div style="font-size:14px;color:#3E4C59;line-height:1.55;font-style:italic;">
                <span style="color:#CBD2D9;font-size:18px;line-height:0;vertical-align:-4px;margin-right:2px;">&ldquo;</span>{hl}<span style="color:#CBD2D9;font-size:18px;line-height:0;vertical-align:-4px;margin-left:2px;">&rdquo;</span>
              </div>
              <div style="font-size:11px;color:#9AA5B1;margin-top:4px;">&mdash; {label}</div>
            </div>""")
        parts.append(f"""
        <div style="margin-top:20px;padding-top:16px;border-top:1px solid #EDF0F3;">
          <div style="font-size:11px;color:#7B8794;text-transform:uppercase;letter-spacing:1.5px;font-weight:600;">In Context</div>
          {''.join(ex_html)}
        </div>""")

    body = "".join(parts)
    return section_card("Word of the Day", word, body)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--word", help="Force a specific word (skip random pick)")
    args = ap.parse_args()
    if args.word:
        # Stub a small render to test rendering for a specific word
        defn = _lookup_definition(args.word)
        if not defn:
            print(f"No definition found for {args.word!r}")
            raise SystemExit(1)
        rng = random.Random(0)
        examples = _find_examples(args.word, NUM_EXAMPLES, rng)
        print(f"Found {len(examples)} example(s) for {args.word!r}:")
        for sent, path in examples:
            print(f"  [{_source_label(path)}]")
            print(f"    {sent[:200]}")
    else:
        print(render())
