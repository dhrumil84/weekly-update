"""Shared text-cleaning helpers used by all fetchers."""
from __future__ import annotations

import re

SMART_QUOTES = {
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "—": " -- ", "–": " -- ", "…": "...",
    "\xa0": " ",
}


def normalize_text(text: str) -> str:
    """Smart-quote normalization + whitespace collapse."""
    for k, v in SMART_QUOTES.items():
        text = text.replace(k, v)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def looks_tabular(line: str) -> bool:
    """Heuristic: drop the line if it looks like a financial-table row.

    True if the ratio of digits/punctuation to alphabetic chars is high, or
    fewer than 4 alphabetic words appear.
    """
    s = line.strip()
    if not s:
        return False
    alpha = sum(1 for c in s if c.isalpha())
    if alpha == 0:
        return True
    non_alpha = sum(1 for c in s if c in "0123456789$,.%()[]/-+")
    if alpha > 0 and non_alpha / max(alpha, 1) > 0.6:
        return True
    words = [w for w in re.findall(r"\b[A-Za-z][A-Za-z'\-]+\b", s) if len(w) > 1]
    if len(words) < 4 and any(c.isdigit() for c in s):
        return True
    return False


def drop_tabular_lines(text: str) -> str:
    """Pass text through line-by-line, dropping lines that look like table rows."""
    return "\n".join(line for line in text.splitlines() if not looks_tabular(line))


def strip_gutenberg_chrome(text: str) -> str:
    """Trim Project Gutenberg header/footer/license boilerplate."""
    start = re.search(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG[^\n]*\*\*\*", text)
    end = re.search(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG[^\n]*\*\*\*", text)
    if start:
        text = text[start.end():]
    if end:
        text = text[:end.start()]
    # Also drop any "Produced by" / "Transcriber's note" preambles
    text = re.sub(r"^Produced by[^\n]*\n", "", text, flags=re.M)
    return text.strip()
