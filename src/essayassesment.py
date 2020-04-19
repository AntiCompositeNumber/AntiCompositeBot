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
import requests
import itertools
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

__version__ = 0.1

site = pywikibot.Site("en", "wikipedia")
session = requests.session()
session.headers.update({"User-Agent": toolforge.set_user_agent("anticompositebot")})
simulate = True

logging.basicConfig(
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
    level=logging.INFO,
    filename="essayimpact.log",
)
# shut pywikibot up
logging.getLogger("pywiki").setLevel(logging.INFO)
logger = logging.getLogger("essayassesment")
logger.setLevel(logging.DEBUG)


@dataclass
class Essay:
    page: pywikibot.Page
    links: Optional[int] = None
    watchers: Optional[int] = None
    views: Optional[int] = None
    score: Optional[int] = None

    def get_views_and_watchers(self):
        title = self.page.title()
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "prop": "info|pageviews",
            "titles": title,
            "formatversion": "2",
            "inprop": "watchers",
            "pvipmetric": "pageviews",
            "pvipdays": "31",
        }
        req = session.get(url, params=params)
        req.raise_for_status()
        data = req.json()["query"]["pages"][0]
        watchers = data.get("watchers", 0)
        views = sum(i if i else 0 for i in list(data["pageviews"].values())[0:30])
        self.views, self.watchers = views, watchers
        return views, watchers

    def get_page_links(self):
        page = self.page
        query = """
        SELECT COUNT(pl_from)
        FROM pagelinks
        WHERE pl_title = %s and pl_namespace = %s"""
        conn = toolforge.connect("enwiki_p")
        with conn.cursor() as cur:
            cur.execute(
                query, (page.title(underscore=True, with_ns=False), page.namespace().id)
            )
            self.links = cur.fetchall()[0][0]
        return self.links

    def calculate_score(self):
        if self.views is None or self.watchers is None:
            self.get_views_and_watchers()
        if self.links is None:
            self.get_page_links()

        self.score = round(self.watchers * 10 + self.views * 2 + self.links / 100, 2)
        return self.score

    def row(self, rank=0):
        wikitext = "|-\n| "
        wikitext += " || ".join(
            str(o)
            for o in (
                rank if rank else "",
                self.page.title(as_link=True, insite=site),
                self.links,
                self.watchers if self.watchers else "&mdash;",
                self.views,
                self.score,
                # (
                #     "{{{{essaycatscore|watchers={0.watchers}"
                #     "|views={0.views}|links={0.links}}}}}"
                # ).format(self),
            )
        )
        wikitext += "\n"
        return wikitext


def iter_project_pages():
    query = """
        SELECT page_namespace - 1, page_title
        FROM templatelinks
        JOIN page ON tl_from = page_id
        WHERE
            tl_title = "WikiProject_Essays"
            and tl_namespace = 10
            and page_namespace in (3, 5, 13)
        """
    conn = toolforge.connect("enwiki_p")
    with conn.cursor() as cur:
        rows = cur.execute(query)
        logger.info(f"{rows} pages found")
        data = cur.fetchall()

    # XXX: Work around pywikibot bug T67262
    namespaces = {2: "User:", 4: "Wikipedia:", 12: "Help:"}

    progress = -1
    for i, ns, title in enumerate(data):
        percent = math.floor(i / rows * 100)
        if (percent > progress) and (percent % 5 == 0):
            logger.info(f"Analyzing pages: {percent}% complete")
            progress = percent
        yield pywikibot.Page(site, title=namespaces[ns] + str(title, encoding="utf-8"))

    logger.info("Analyzing pages: 100% complete")


def construct_table(data):
    logger.info("Constructing table")
    table = f"""Pages where the talk page transcludes {{{{tl|WikiProject Essays}}}} sorted
by [[Wikipedia:WikiProject_Wikipedia_essays/Assessment#Impact_scale|impact score]].
Number of watchers is included if the result is greater than 29.
Last updated {datetime.utcnow().strftime("%H:%M, %d %B %Y (UTC)")}
{{| class="wikitable sortable plainlinks" style="width:100%; margin:auto"
|- style="white-space:nowrap;"
! No.
! Page
! Incoming links
! Watchers
! Pageviews
! Score
"""
    table = "".join(
        itertools.chain(
            [table],
            [
                essay.row(rank=i + 1)
                for i, essay in enumerate(
                    sorted(data, key=lambda e: e.score, reverse=True)
                )
            ],
            ["|}"],
        )
    )

    return table


def check_runpage() -> None:
    """Raises pywikibot.UserBlocked if on-wiki runpage is not True"""
    page = pywikibot.Page(site, "User:AntiCompositeBot/EssayImpact/Run")
    if not page.text.endswith("True"):
        raise pywikibot.UserBlocked("Runpage is false, quitting")


def save_page(text):
    page = pywikibot.Page(
        site, "Wikipedia:WikiProject Wikipedia essays/Assessment/Links"
    )
    logger.info(f"Saving to {page.title()}")
    if text and page.text != text:
        page.text = text
        page.save(
            summary=f"Updating assesment table (Bot) (EssayImpact {__version__}",
            minor=False,
            botflag=False,
            quiet=True,
        )
        logging.info(f"Page {page.title(as_link=True)} saved")


def main():
    logger.info("Starting up")
    data = []
    for page in iter_project_pages():
        essay = Essay(page)
        essay.calculate_score()
        data.append(essay)
    table = construct_table(data)
    if not simulate:
        check_runpage()
        save_page(table)
    else:
        print(table)
    logger.info("Finished")


if __name__ == "__main__":
    main()
