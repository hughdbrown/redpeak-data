#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
# "click",
# "requests",
# ]
# ///
import csv
import filecmp
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

import click
import requests

FORMAT = '%(asctime)s %(levelname)s %(message)s'
log_level = os.environ.get('LOGLEVEL', 'WARNING').upper()
logging.basicConfig(
    format=FORMAT,
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=log_level,
)
logger = logging.getLogger(__name__)

OUTPUT_HEADER = "date  bdrm  price unit  area\n"

SIGHTMAP_EMBED_RE = re.compile(r'sightmap\.com/embed/([a-z0-9]+)(?![.a-z0-9])')
SIGHTMAP_API_HREF_RE = re.compile(
    r'"href":"(https:\\?/\\?/sightmap\.com\\?/app\\?/api\\?/v1\\?/[^"]*sightmaps\\?/[0-9]+)"'
)


def process_line(line):
    regexes = [
        re.compile(r'class=".*?"'),
        re.compile(r'aria-label=".*?"'),
        re.compile(r'data-spaces-href=".*?"'),
        re.compile(r'data-spaces-inventory-href=".*?"'),
        re.compile(r'data-spaces-sort-plan-name=".*?"'),
        re.compile(r'data-spaces-community=".*?"'),
    ]

    line = line.strip().replace("<article", "").replace(">", "")
    for regex in regexes:
        line = regex.sub("", line)

    items = [item for item in line.strip().split(' ') if item]
    x = {}
    for item in items:
        try:
            k, v = item.split('=')
        except ValueError:
            print(f"Missing divider: '{item}'")
            raise
        x[k] = v.replace('"', '')
    return x


def _output_paths(property_name: str, data_dir: Path) -> tuple[Path, Path]:
    output: Path = data_dir.joinpath(property_name)
    if not output.exists():
        logger.info(f"Creating {output}")
        output.mkdir(parents=True)
    output_file: Path = output.joinpath(f"rents-{datetime.now():%Y-%m-%d}.txt")
    return output, output_file


def _write_rows(output_file: Path, rows: list[tuple[str, str, str, str, str]]) -> None:
    rows_sorted = sorted(rows, key=lambda r: (r[1], r[0]))  # (bdrm, date)
    with output_file.open("w", encoding="utf-8") as handle:
        handle.write(OUTPUT_HEADER)
        for (date, bdrm, price, unit, area) in rows_sorted:
            handle.write(f"{date} {bdrm} {price} {unit} {area}\n")


def _dedup(output: Path, output_file: Path) -> None:
    prior = max(
        (p for p in output.glob("rents-*.txt") if p != output_file),
        default=None,
        key=lambda p: p.name,
    )
    if prior is not None and filecmp.cmp(prior, output_file, shallow=False):
        logger.info(f"{output_file} matches {prior}; removing duplicate")
        output_file.unlink()


def do_property_html(url: str, property_name: str, data_dir: Path) -> None:
    logger.info(f"[html] {url = } {property_name = }")
    output, output_file = _output_paths(property_name, data_dir)

    full_url = f"{url}?spaces_sort=pr_asc&spaces_tab=unit"
    resp = requests.get(full_url)
    if not resp.ok:
        logger.error(f"{full_url} -> {resp.status_code}")
        return

    unit_re = re.compile(r"^.*Unit [0-9]+")
    line_iter = (line.strip().decode('utf-8') for line in resp.iter_lines())
    parsed = [
        process_line(line) for line in line_iter
        if line and unit_re.match(line) and not line.startswith("<a ")
    ]
    if not parsed:
        logger.info("No data")
        return

    rows = [
        (
            d['data-spaces-soonest'],
            d['data-spaces-sort-bed'],
            d['data-spaces-sort-price'],
            d['data-spaces-unit'],
            d['data-spaces-sort-area'],
        )
        for d in parsed
    ]
    _write_rows(output_file, rows)
    _dedup(output, output_file)


def do_property_json(sightmap_url: str, property_name: str, data_dir: Path) -> None:
    logger.info(f"[json] {sightmap_url = } {property_name = }")
    output, output_file = _output_paths(property_name, data_dir)

    resp = requests.get(sightmap_url)
    if not resp.ok:
        logger.error(f"{sightmap_url} -> {resp.status_code}")
        return

    data = resp.json()['data']
    bedrooms_by_plan = {fp['id']: fp['bedroom_count'] for fp in data.get('floor_plans', [])}
    units = data.get('units', [])
    if not units:
        logger.info("No data")
        return

    rows = [
        (
            u['available_on'],
            str(bedrooms_by_plan.get(u['floor_plan_id'], '')),
            str(u['price']),
            u['unit_number'],
            str(u['area']),
        )
        for u in units
        if u.get('available_on') is not None
    ]
    _write_rows(output_file, rows)
    _dedup(output, output_file)


def discover_sightmap_url(property_url: str) -> str | None:
    """Fetch property page → SightMap embed hash → JSON API href."""
    resp = requests.get(property_url)
    if not resp.ok:
        logger.error(f"{property_url} -> {resp.status_code}")
        return None
    m = SIGHTMAP_EMBED_RE.search(resp.text)
    if not m:
        logger.info(f"No SightMap embed in {property_url}")
        return None
    embed_url = f"https://sightmap.com/embed/{m.group(1)}"
    resp2 = requests.get(embed_url)
    if not resp2.ok:
        logger.error(f"{embed_url} -> {resp2.status_code}")
        return None
    m2 = SIGHTMAP_API_HREF_RE.search(resp2.text)
    if not m2:
        logger.info(f"No API href in {embed_url}")
        return None
    return json.loads(f'"{m2.group(1)}"')


@click.group()
def cli():
    pass


@cli.command()
@click.option("--csv-path", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=Path("properties.csv"), show_default=True,
              help="CSV file with url,name[,sightmap_url] columns.")
@click.option("--data-dir", type=click.Path(file_okay=False, path_type=Path),
              default=Path("data"), show_default=True,
              help="Directory to write per-property data into.")
@click.option("--source", type=click.Choice(["auto", "json", "html"]), default="auto",
              show_default=True,
              help="auto: JSON if sightmap_url is set, else HTML.")
def scrape(csv_path: Path, data_dir: Path, source: str) -> None:
    """Scrape rental data for every property in the CSV."""
    with csv_path.open() as handle:
        reader = csv.DictReader(handle)
        for d in reader:
            logger.debug(f"{d = }")
            sightmap_url = (d.get("sightmap_url") or "").strip()
            use_json = source == "json" or (source == "auto" and sightmap_url)
            if use_json:
                if not sightmap_url:
                    logger.warning(f"{d['name']}: --source=json but no sightmap_url; skipping")
                    continue
                do_property_json(sightmap_url, d["name"], data_dir)
            else:
                do_property_html(d["url"], d["name"], data_dir)


@cli.command()
@click.option("--csv-path", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=Path("properties.csv"), show_default=True)
@click.option("--force", is_flag=True,
              help="Re-discover even if sightmap_url is already set.")
def discover(csv_path: Path, force: bool) -> None:
    """Populate the sightmap_url column in the CSV by inspecting each property page."""
    with csv_path.open() as handle:
        rows = list(csv.DictReader(handle))

    fieldnames = ["url", "name", "sightmap_url"]
    for row in rows:
        existing = (row.get("sightmap_url") or "").strip()
        if existing and not force:
            continue
        url = discover_sightmap_url(row["url"])
        row["sightmap_url"] = url or ""
        logger.info(f"{row['name']}: {row['sightmap_url'] or '(none)'}")

    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


if __name__ == '__main__':
    cli()
