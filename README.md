# redpeak-data

Historical record of listed rental prices for [RedPeak](https://redpeak.com/) Denver-area properties, captured daily via the [git-scraping pattern](https://simonwillison.net/2020/Oct/9/git-scraping/).

## How it works

1. A GitHub Actions cron job runs `redpeak-vacancy.py` once per day.
2. The script reads `properties.csv` (columns: `url,name`).
3. For each property it fetches the apartments page, parses the listing tags, and writes a sorted summary to `data/<property-name>/rents-<YYYY-MM-DD>.txt`.
4. If the new file is byte-identical to the most recent prior file in that property's directory, the new file is deleted — so commits only land when something actually changed.
5. The workflow then commits and pushes any changes, building up an append-only history visible in `git log`.

Each row in a per-day file is:

```
num  date  bdrm  price unit  area
0: 2026-01-31 1 1732 07103 713
```

## Stack

- Python 3.11+
- [`requests`](https://pypi.org/project/requests/) for HTTP
- [`click`](https://pypi.org/project/click/) for CLI options
- [`uv`](https://github.com/astral-sh/uv) — the script is a [PEP 723](https://peps.python.org/pep-0723/) single-file script with inline dependencies

## Running locally

```sh
./redpeak-vacancy.py                  # scrape all properties in properties.csv
./redpeak-vacancy.py --csv-path foo.csv --data-dir out
LOGLEVEL=INFO ./redpeak-vacancy.py    # verbose
```

`uv` resolves the inline `requests` / `click` dependencies on first run.

## Layout

```
.
├── redpeak-vacancy.py          # scraper (uv inline-deps script)
├── properties.csv              # url,name list of properties to scrape
├── data/<property>/rents-*.txt # per-property daily snapshots (versioned)
├── docs/
│   ├── prompt.md               # authoritative spec
│   └── project-design.md       # source URLs + inspiration links
└── .github/workflows/scrape.yml # daily cron job
```

## Inspiration

- Simon Willison, [_Git scraping: track changes over time by scraping to a Git repository_](https://simonwillison.net/2020/Oct/9/git-scraping/)
- Reference implementation: [`simonw/ca-fires-history`](https://github.com/simonw/ca-fires-history)
