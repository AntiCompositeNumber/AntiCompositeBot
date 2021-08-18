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


import pywikibot  # type: ignore
import toolforge  # type: ignore
import utils
import logging
import logging.config

__version__ = "0.1"

logging.config.dictConfig(
    utils.logger_config("uncat", level="VERBOSE", filename="stderr")
)
logger = logging.getLogger("uncat")

site = pywikibot.Site("commons", "commons")


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
    out = """{| class="wikitable"
!File!!Links
|-
"""
    out += "\n|-\n".join(f"|[[:File:{file}]]||{count}" for file, count in data)
    out += "\n|}"
    return out


def save_page(table):
    utils.check_runpage(site, "Uncat")
    page = pywikibot.Page(site, "User:AntiCompositeBot/Uncat")
    utils.save_page(
        text=table,
        page=page,
        summary=f"Updating report (Bot) (Uncat {__version__})",
        mode="replace",
        bot=False,
    )


def main():
    data = run_query()
    table = make_table(data)
    save_page(table)
