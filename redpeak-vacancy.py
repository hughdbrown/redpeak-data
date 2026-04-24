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
from datetime import datetime
import logging
import os
from pathlib import Path
from re import compile
from sys import stdin
import re

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

"""
tags = {
    class="spaces__unit price_1500-2000 area_500-750 floor_2936 community-timber-creek 1bed 1bath has_tour"
    data-spaces-asset="829"
    aria-label="Unit 07202"
    data-spaces-soonest="2024-07-07"
    data-spaces-sort-date="1720310400"
    data-spaces-sort-price="1759"
    data-spaces-sort-area="713"
    data-spaces-sort-bed="1"
    data-spaces-unit="07202"
    data-spaces-unit-id="161761"
    data-spaces-unit-floor="2936"
    data-spaces-obj="unit"
    data-spaces-unavailable="false"
    data-spaces-available="true"
    data-spaces-specials-content=""
    data-spaces-sort-plan-name="CatTail"
    data-spaces-href="?spaces_tab=unit-detail&detail=161761"
    data-spaces-inventory-href="https://redpeak.com/property//apartments/?spaces_tab=unit-detail&detail=161761#spaces_anchor"
}
"""

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
        except ValueError as err:
            print(f"Missing divider: '{item}'")
            raise
        x[k] = v.replace('"', '')
    return x


def do_property(url: str, property_name: str, data_dir: Path):
    logger.info(f"{url = } {property_name = }")

    now = datetime.now()
    output: Path = data_dir.joinpath(property_name)
    if not output.exists():
        logger.info(f"Creating {str(output)}")
        output.mkdir(parents=True)
    output_file: Path = output.joinpath(f"rents-{now:%Y-%m-%d}.txt")

    full_url = f"{url}?spaces_sort=pr_asc&spaces_tab=unit"
    logger.info(f"{full_url = }")
    resp = requests.get(full_url)
    if not resp.ok:
        msg = f"{full_url} not found"
        logger.error(msg)

    re = compile(r"^.*Unit [0-9]+")
    line_iter = (line.strip().decode('utf-8') for line in resp.iter_lines())
    lines = [process_line(line) for line in line_iter if line and re.match(line) and not line.startswith("<a ")]
    if not lines:
        logger.info("No data")
        return None
 
    tags = [
        'data-spaces-soonest',
        'data-spaces-sort-bed',
        'data-spaces-sort-price',
        'data-spaces-unit',
        'data-spaces-sort-area',
    ]

    logger.info(f"Creating {str(output)}")
    with output_file.open("w", encoding="utf-8") as handle:
        handle.write("num  date  bdrm  price unit  area\n")
        for i, d in enumerate(sorted(
            lines,
            key=lambda x: (x[tags[1]], x[tags[0]])
        )):
            s = " ".join((d[tag] for tag in tags))
            handle.write(f"{i}: {s}\n")

        """
        today = datetime.today()
        for i, d in enumerate(sorted(
            lines,
            key=lambda x: (x[tags[1]], x[tags[0]])
        )):
            soonest = datetime.strptime(d[tags[0]], "%Y-%m-%d")
            if (days := (today - soonest).days) > 0:
                rent = int(d[tags[2]])
                handle.write(f"{i}: {soonest:%Y-%m-%d} {days} {rent} {rent * (days / 30):.02f}\n")
        """

    prior = max(
        (p for p in output.glob("rents-*.txt") if p != output_file),
        default=None,
        key=lambda p: p.name,
    )
    if prior is not None and filecmp.cmp(prior, output_file, shallow=False):
        logger.info(f"{output_file} matches {prior}; removing duplicate")
        output_file.unlink()


@click.command()
@click.option(
    "--csv-path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path("properties.csv"),
    show_default=True,
    help="CSV file with url,name columns.",
)
@click.option(
    "--data-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data"),
    show_default=True,
    help="Directory to write per-property data into.",
)
def main(csv_path: Path, data_dir: Path):
    with csv_path.open() as handle:
        reader = csv.DictReader(handle)
        for d in reader:
            logger.debug(f"{d = }")
            do_property(d["url"], d["name"], data_dir)


if __name__ == '__main__':
    main()

