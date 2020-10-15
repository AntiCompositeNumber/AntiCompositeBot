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

import pywikibot  # type: ignore
import logging
import logging.config
import sys
import toolforge  # type: ignore
import string

from typing import Iterator, Tuple

import utils

__version__ = "0.2"
site = pywikibot.Site("en", "wikipedia")

logging.config.dictConfig(
    utils.logger_config("dcs_redir", level="VERBOSE", filename="dcs_redir.log")
)
logger = logging.getLogger("dcs_redir")

simulate = True


def iter_pages_and_targets() -> Iterator[Tuple[pywikibot.Page, str]]:
    conn = toolforge.connect("enwiki_p")
    query = """
SELECT
  CONCAT("Talk:", com.page_title) as title,
  CONCAT("Talk:", target.page_title) as target
FROM
  page com
  JOIN page target ON target.page_title = REPLACE(com.page_title, "/Comments", "")
WHERE
  com.page_namespace = 1
  AND target.page_namespace = 1
  AND com.page_title LIKE "%/Comments"
  AND com.page_is_redirect = 0
  AND com.page_len = 0
  AND target.page_is_redirect = 0
"""
    with conn.cursor() as cur:
        cur.execute(query)
        data = cur.fetchall()

    for title, target in data:
        yield (
            pywikibot.Page(site, str(title, encoding="utf-8")),
            str(target, encoding="utf-8"),
        )


def update_page_text(page: pywikibot.Page, target: str) -> None:
    new_text = string.Template(
        """#REDIRECT [[$target]]

{{Redirect category shell|
{{R from subpage}}
{{R from merge}}
}}
"""
    ).substitute(target=target)
    summary = f"Redirecting to {target} per [[WP:DCS]] (dcs_redir {__version__})"
    if simulate:
        logger.debug(f"Simulating {page.title(as_link=True)}: {summary}")
        logger.debug(new_text)
    else:
        utils.save_page(
            text=new_text,
            page=page,
            summary=summary,
            bot=True,
            minor=True,
            mode="replace",
        )


def main(limit: int = 0):
    total = 0
    throttle = utils.Throttle(60)
    for page, target in iter_pages_and_targets():
        if limit and limit <= total:
            break
        else:
            total += 1
        logger.info(f"{total}: Redirecting {page.title(as_link=True)} to {target}")
        update_page_text(page, target)
        throttle.throttle()
    logger.info("Finished")


if __name__ == "__main__":
    try:
        lim = int(sys.argv[1])
    except IndexError:
        lim = 0
    main(lim)
