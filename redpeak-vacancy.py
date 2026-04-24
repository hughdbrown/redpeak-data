#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
# "requests",
# ]
# ///
import csv
from datetime import datetime
import logging
import os
from pathlib import Path
from re import compile
from sys import stdin
import re

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


def do_property(url: str, property_name: str):
    logger.info(f"{url = } {property_name = }")

    now = datetime.now()
    output: Path = Path("data").joinpath(property_name)
    if not output.exists():
        logger.info(f"Creating {str(output)}")
        output.mkdir() 
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
    
if __name__ == '__main__':
    with open("properties.csv") as handle:
        # fields = handle.readline().strip().split(',')
        # logger.debug(f"{fields = }")
        reader = csv.DictReader(handle) # , fields)
        for d in reader:
            logger.debug(f"{d = }")
            url, property_name = d["url"], d["name"]
            do_property(url, property_name)

