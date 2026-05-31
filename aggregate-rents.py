#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
# "click",
# ]
# ///
"""Aggregate per-apartment rent history for one complex.

Reads the daily snapshot files in ``data/<complex>/rents-YYYY-MM-DD.txt``,
loads ``(scrape_date, apartment, rent)`` into a throwaway SQLite database,
and reports for every apartment its opening, low, high, and closing rent.

The "date" axis is the *scrape date* taken from each filename -- i.e. when we
observed the rent -- not the availability ``date`` column inside the file.
That is what makes "first/last rent by date" a meaningful time series.

The first historical file format (header ``num  date  bdrm ...``) was only
emitted for a few days and is skipped.
"""
import csv
import logging
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

import click

FORMAT = '%(asctime)s %(levelname)s %(message)s'
log_level = os.environ.get('LOGLEVEL', 'WARNING').upper()
logging.basicConfig(
    format=FORMAT,
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=log_level,
)
logger = logging.getLogger(__name__)

# rents-2026-05-14.txt -> 2026-05-14
SCRAPE_DATE_RE = re.compile(r"rents-(\d{4}-\d{2}-\d{2})\.txt$")

# The canonical (current) format. The older "num  date  bdrm ..." format is skipped.
CANONICAL_HEADER = "date  bdrm  price unit  area"

# Column order within a canonical data line: date bdrm price unit area
COL_PRICE = 2
COL_UNIT = 3

CREATE_TABLE = """
CREATE TABLE rents (
    date  TEXT NOT NULL,
    apt   TEXT NOT NULL,
    rent  INTEGER NOT NULL,
    PRIMARY KEY (date, apt)
)
"""

# For each apartment: opening rent (earliest scrape), closing rent (latest
# scrape), and the low/high seen across all scrapes.
AGGREGATE_QUERY = """
SELECT apt, open_rent, low_rent, high_rent, close_rent
FROM (
    SELECT
        apt,
        FIRST_VALUE(rent) OVER w AS open_rent,
        LAST_VALUE(rent)  OVER w AS close_rent,
        MIN(rent) OVER (PARTITION BY apt) AS low_rent,
        MAX(rent) OVER (PARTITION BY apt) AS high_rent,
        ROW_NUMBER() OVER (PARTITION BY apt ORDER BY date) AS rn
    FROM rents
    WINDOW w AS (
        PARTITION BY apt ORDER BY date
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    )
)
WHERE rn = 1
ORDER BY apt
"""


def iter_snapshot_rows(complex_dir: Path):
    """Yield (scrape_date, apt, rent) for every canonical-format snapshot line."""
    for path in sorted(complex_dir.glob("rents-*.txt")):
        m = SCRAPE_DATE_RE.search(path.name)
        if not m:
            logger.warning(f"{path.name}: cannot parse scrape date; skipping")
            continue
        scrape_date = m.group(1)

        with path.open(encoding="utf-8") as handle:
            header = handle.readline().rstrip("\n")
            if header.strip() != CANONICAL_HEADER:
                logger.info(f"{path.name}: non-canonical header {header!r}; skipping file")
                continue

            for lineno, line in enumerate(handle, start=2):
                fields = line.split()
                if not fields:
                    continue
                if len(fields) < COL_UNIT + 1:
                    logger.warning(f"{path.name}:{lineno}: too few fields {fields!r}; skipping")
                    continue
                apt = fields[COL_UNIT]
                try:
                    rent = int(fields[COL_PRICE])
                except ValueError:
                    logger.warning(f"{path.name}:{lineno}: non-integer rent {fields[COL_PRICE]!r}; skipping")
                    continue
                yield scrape_date, apt, rent


def aggregate(complex_dir: Path) -> list[tuple[str, int, int, int, int]]:
    """Load snapshots into a temporary SQLite db and return aggregated rows."""
    fd, db_path = tempfile.mkstemp(suffix=".sqlite", prefix="rents-")
    os.close(fd)
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(CREATE_TABLE)
            # One file per scrape date, unique apt per file -> no real conflicts,
            # but OR REPLACE keeps us robust against any duplicate key.
            conn.executemany(
                "INSERT OR REPLACE INTO rents (date, apt, rent) VALUES (?, ?, ?)",
                iter_snapshot_rows(complex_dir),
            )
            conn.commit()
            return conn.execute(AGGREGATE_QUERY).fetchall()
        finally:
            conn.close()
    finally:
        Path(db_path).unlink(missing_ok=True)
        logger.info(f"Removed temporary database {db_path}")


@click.command()
@click.argument("complex_name")
@click.option("--data-dir", type=click.Path(file_okay=False, path_type=Path),
              default=Path("data"), show_default=True,
              help="Directory containing per-complex snapshot folders.")
@click.option("--no-header", is_flag=True, help="Omit the CSV header row.")
def main(complex_name: str, data_dir: Path, no_header: bool) -> None:
    """Aggregate rent history for COMPLEX_NAME (a folder under --data-dir).

    Outputs CSV rows: apt, open_rent, low_rent, high_rent, close_rent
    """
    complex_dir = data_dir / complex_name
    if not complex_dir.is_dir():
        raise click.BadParameter(f"{complex_dir} is not a directory")

    rows = aggregate(complex_dir)
    if not rows:
        logger.warning(f"{complex_dir}: no canonical-format data found")
    else:
        writer = csv.writer(sys.stdout)
        if not no_header:
            writer.writerow(["apt", "open_rent", "low_rent", "high_rent", "close_rent"])
        writer.writerows(rows)



if __name__ == "__main__":
    main()
