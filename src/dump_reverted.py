#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 AntiCompositeNumber

import csv
import os
import toolforge
import acnutils

logger = acnutils.getInitLogger("dump-reverted", level="VERBOSE", filename="stderr")

START_DATE = "20201020000000"
END_DATE = "20230420240000"
WIKIS = [
    "arwiki",
    "azwiki",
    "cawiki",
    "ckbwiki",
    "cswiki",
    "dewiki",
    "enwiki",
    "eswiki",
    "fawiki",
    "fiwiki",
    "frwiki",
    "hewiki",
    "idwiki",
    "itwiki",
    "jawiki",
    "nlwiki",
    "nowiki",
    "plwiki",
    "ruwiki",
    "svwiki",
    "zhwiki",
]
OUTPUT_DIR = "/data/project/anticompositebot/www/static/dump_reverted"


def do_query(wiki: str) -> dict[str, dict[str, int]]:
    query = """
SELECT
    LEFT(rev_timestamp, 8) as `day`,
    ct_id IS NOT NULL as `reverted`,
    COUNT(rev_id) as `edits`
FROM revision
JOIN page ON rev_page = page_id
LEFT JOIN change_tag ON
    ct_rev_id = rev_id
    AND ct_tag_id = (SELECT ctd_id FROM change_tag_def WHERE ctd_name = "mw-reverted")
WHERE
    rev_timestamp > %s
    AND rev_timestamp < %s
GROUP BY 1, 2
WITH ROLLUP"""
    logger.info(f"Querying {wiki}")
    conn = toolforge.connect(wiki, cluster="analytics")
    with conn.cursor() as cur:
        cur.execute(query, args=[START_DATE, END_DATE])
        raw_data = cur.fetchall()

    data: dict[str, dict[str, int]] = {}
    for day, reverted, edits in raw_data:
        if day is None:
            continue
        day = str(day, encoding="utf-8")
        if reverted == 0:
            field = "unreverted"
        elif reverted == 1:
            field = "reverted"
        elif reverted is None:
            field = "total"
        else:
            raise ValueError(reverted)

        data.setdefault(day, {})[field] = edits

    return data


def dump_file(wiki: str, data) -> None:
    with open(os.path.join(OUTPUT_DIR, f"{wiki}.csv"), "w", newline="") as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(["day", "unreverted", "reverted", "total"])
        for day, edits in data.items():
            csvwriter.writerow(
                [
                    day,
                    edits.get("unreverted", 0),
                    edits.get("reverted", 0),
                    edits.get("total", 0),
                ]
            )

    logger.info(f"Wrote {wiki}.csv")


def main():
    for wiki in WIKIS:
        try:
            data = do_query(wiki)
        except Exception as err:
            logger.exception(err)
        else:
            dump_file(wiki, data)


if __name__ == "__main__":
    main()
