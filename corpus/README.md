# Corpus

Source material for the (future) word-of-the-day section. Plain `.txt` files only — no binaries, no PDFs in the committed tree.

## Layout

```
corpus/
├── scotus/        # SCOTUS dissents + concurrences, one file per justice
├── pg/            # Paul Graham essays, one file per essay
├── buffett/       # Berkshire Hathaway annual letters, one file per year
├── gutenberg/     # Curated Project Gutenberg works (Russell, James, etc.)
├── federalist/    # The Federalist Papers
└── custom/        # Drop your own .txt files here
```

## Sources

| Subdir | Source | License |
|---|---|---|
| `scotus/` | [CourtListener API](https://www.courtlistener.com/api/) | Public domain (U.S. gov works) |
| `pg/` | [paulgraham.com](http://www.paulgraham.com/articles.html) | Public web, scraping explicitly welcomed by author |
| `buffett/` | [berkshirehathaway.com/letters/](https://www.berkshirehathaway.com/letters/letters.html) | Public web, freely distributed by author |
| `gutenberg/` | [gutenberg.org](https://www.gutenberg.org) | Public domain |
| `federalist/` | [gutenberg.org #1404](https://www.gutenberg.org/ebooks/1404) | Public domain |
| `custom/` | You | Your call |

## Refreshing

Each fetcher is in `scripts/` and is idempotent — it skips files that already exist unless `--refresh` is passed.

```powershell
# One-time local setup
pip install -r requirements-dev.txt

# Refresh individual sources
python -m scripts.fetch_scotus
python -m scripts.fetch_pg
python -m scripts.fetch_buffett
python -m scripts.fetch_gutenberg

# Force re-download
python -m scripts.fetch_scotus --refresh
```

After refreshing, `git add corpus/ && git commit && git push`. The Sunday CI just reads from these files — it does not run the fetchers.

## Preprocessing notes

- **SCOTUS**: strips case captions, syllabi, citations (U.S. / S.Ct. / L.Ed. / slip op.), parenthetical citation phrases ("citing X", "quoting Y", "internal quotation marks omitted"), section symbols, footnote markers.
- **PG**: drops "Want to start a startup?" header, "Notes" footer, "Thanks to X for reading drafts" lines, footnote markers.
- **Buffett**: HTML letters → `<table>` elements removed entirely before text extraction. PDF letters → `pdfplumber` detects table bounding boxes and masks them out. Second-pass numeric-line filter catches strays.
- **Gutenberg**: trims standard `*** START OF... ***` / `*** END OF... ***` boilerplate and any Table of Contents block.

## Adding your own text

Drop `.txt` files into `corpus/custom/`. The future word-of-day section will read from every subdirectory uniformly. No fetcher needed.
