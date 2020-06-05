#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: Apache-2.0


# Copyright 2020 AntiCompositeNumber

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import pywikibot
import toolforge
import re
import sys
import time
import utils
import logging
import logging.config

__version__ = "0.4"

logging.config.dictConfig(
    utils.logger_config("wla_append", filename="stderr", level="VERBOSE")
)
logger = logging.getLogger("wla_append")

site = pywikibot.Site("commons", "commons")
last_edit = 0


def iter_files():
    conn = toolforge.connect("commonswiki")
    query = """
        SELECT CONCAT("File:", page_title)
        FROM page
        JOIN categorylinks ON cl_from = page_id
        WHERE
            cl_to IN (
                SELECT page_title
                FROM page
                JOIN categorylinks ON cl_from = page_id
                WHERE
                    cl_to = "Images_from_Wiki_Loves_Africa_2020"
                    and cl_type = "subcat"
                    and cl_sortkey != " "
            )
            and page_id NOT IN (
                SELECT cl_from
                FROM categorylinks
                WHERE
                    cl_to = "Images_from_Wiki_Loves_Africa_2020"
            )
            and page_namespace = 6
    """
    with conn.cursor() as cur:
        cur.execute(query)
        for title in cur.fetchall():
            yield pywikibot.Page(site, str(title[0], encoding="utf-8"))


def do_replacements(text):
    text = re.sub(
        r"\n\n\[\[ *Category:", "\n{{Wiki Loves Africa 2020}}\n\n[[Category:", text,
    )
    if not re.search(
        r"\[\[ *Category:Images from Wiki Loves Africa 2020 to check *\]\]", text
    ):
        text = re.sub(
            r"\n\n\[\[ *Category:",
            "\n\n[[Category:Images from Wiki Loves Africa 2020 to check]]\n[[Category:",
            text,
        )

    return text


def throttle():
    global last_edit
    now = time.monotonic()
    diff = round(60 - (now - last_edit), 2)
    if diff > 0:
        logger.debug(f"Sleeping for {diff} seconds")
        time.sleep(diff)
    last_edit = time.monotonic()


def run_check():
    runpage = pywikibot.Page(site, "User:AntiCompositeBot/WLA Tagging/Run")
    run = runpage.text.strip().endswith("True")
    if run is False:
        raise pywikibot.UserBlocked("Runpage is false")


def main(limit=0):
    for i, page in enumerate(iter_files()):
        if limit and i >= limit:
            break
        logger.info(f"{i}: {page.title()}")
        new_wikitext = do_replacements(page.text)
        if new_wikitext and new_wikitext != page.text:
            page.text = new_wikitext
            throttle()
            run_check()
            page.save(
                summary=(
                    "Wiki Loves Africa 2020 tagging and categorization "
                    f"(Task 3 v{__version__})"
                ),
                watch="nochange",
                minor=False,
                # botflag=True,
            )

    logger.info("Done")


if __name__ == "__main__":
    main(limit=int(sys.argv[1]))
