#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: Apache-2.0


# Copyright 2021 AntiCompositeNumber

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import toolforge  # type: ignore
import utils
import logging
import logging.config
import datetime

__version__ = "0.2"

logging.config.dictConfig(utils.logger_config("uncat", level="VERBOSE"))
logger = logging.getLogger("uncat")


def run_query():
    query = """
SELECT page_title, COUNT(*)
FROM page
JOIN templatelinks ON tl_from = page_id
JOIN globalimagelinks ON page_title = gil_to
WHERE
    tl_title = "Uncategorized"
    AND tl_namespace = 10
    AND page_namespace = 6
GROUP BY page_id
ORDER BY COUNT(*) DESC
"""
    conn = toolforge.connect("commonswiki_p")
    with conn.cursor() as cur:
        cur.execute(query)
        data = cur.fetchall()
    for file, count in data:
        yield str(file, encoding="utf-8"), count


def make_table(data):
    out = f"""
<!DOCTYPE html>
<html>
<body>
<p>Last updated {datetime.datetime.now().ctime()}</p>
<table>
<tr><th>File</th><th>Links</th></tr>
!File!!Links
|-
"""
    out += "\n".join(
        f"<tr><td><a href='https://commons.wikimedia.org/wiki/File:{file}'>"
        f"File:{file}</a></td><td>{count}</td></tr>"
        for file, count in data
    )
    out += "</table></body></html>"
    return out


def save_page(table):
    if utils.on_toolforge():
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
