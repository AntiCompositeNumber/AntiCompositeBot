#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2021 AntiCompositeNumber

import toolforge  # type: ignore
import acnutils
import datetime

__version__ = "0.3"

logger = acnutils.getInitLogger("uncat", level="VERBOSE")


def run_query():
    query = """
SELECT page_title, COUNT(*)
FROM page
JOIN templatelinks ON tl_from = page_id
JOIN linktarget ON lt_id = tl_target_id
JOIN globalimagelinks ON page_title = gil_to
WHERE
    lt_title = "Uncategorized"
    AND lt_namespace = 10
    AND page_namespace = 6
GROUP BY page_id
ORDER BY COUNT(*) DESC
"""
    conn = toolforge.connect("commonswiki_p")
    with conn.cursor() as cur:
        cur.execute(query)
        data = cur.fetchall()
    for file, count in data:
        if count >= 20:
            yield str(file, encoding="utf-8"), count


def make_table(data):
    out = f"""
<!DOCTYPE html>
<html>
<body>
<p>Last updated {datetime.datetime.now().ctime()}</p>
<table>
<tr><th>File</th><th>Links</th></tr>
"""
    out += "\n".join(
        f"<tr><td><a href='https://commons.wikimedia.org/wiki/File:{file}'>"
        f"File:{file}</a></td><td>{count}</td></tr>"
        for file, count in data
    )
    out += "</table></body></html>"
    return out


def save_page(table):
    if acnutils.on_toolforge():
        filename = "/data/project/anticompositebot/www/static/uncat.html"
    else:
        filename = "uncat.html"
    with open(filename, "w") as f:
        f.write(table)


def main():
    logger.info("Starting up")
    data = run_query()
    table = make_table(data)
    logger.info("Query complete, saving page")
    save_page(table)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        logger.exception(err)
        raise
