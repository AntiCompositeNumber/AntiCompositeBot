#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2020 AntiCompositeNumber

"""Adjust categorization for Wiki Loves Africa 2020 files

This code was written for a one-off task in 2020.[1] It is no longer actively
maintained.

.. [1] https://commons.wikimedia.org/wiki/Commons:Bots/Requests/AntiCompositeBot_3

:status: archived
:author: AntiCompositeNumber
"""

import pywikibot  # type: ignore
import toolforge
import re
import sys
import time
import acnutils as utils

__version__ = "0.5"

logger = utils.getInitLogger("wla_append", filename="stderr", level="VERBOSE")

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
        r"\n\n\[\[ *Category:",
        "\n{{Wiki Loves Africa 2020}}\n\n[[Category:",
        text,
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
    utils.check_runpage(site, task="WLA Tagging")


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
