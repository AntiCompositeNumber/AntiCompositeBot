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
import toolforge
import requests
import itertools
import logging
import math
import json
from string import Template
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple, Iterator, Iterable, cast, Dict, Union

__version__ = 0.2

site = pywikibot.Site("en", "wikipedia")
session = requests.session()
session.headers.update({"User-Agent": toolforge.set_user_agent("anticompositebot")})
simulate = False

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
    score: Optional[float] = None

    def get_views_and_watchers(self) -> Tuple[int, int]:
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

    def get_page_links(self) -> int:
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
            self.links = cast(Tuple[Tuple[int]], cur.fetchall())[0][0]
        return self.links

    def calculate_score(
        self,
        weights: Dict[str, Union[int, float]] = {
            "watchers": 10,
            "views": 2,
            "links": 0.01,
        },
    ) -> float:
        if self.views is None or self.watchers is None:
            self.get_views_and_watchers()
        if self.links is None:
            self.get_page_links()
        assert all(val is not None for val in [self.views, self.watchers, self.links])

        self.score = round(
            self.watchers * weights["watchers"]
            + self.views * weights["views"]
            + self.links * weights["links"],
            2,
        )
        return self.score

    def row(self, rank: int = 0) -> str:
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

    def data_row(self, key: str, rank: int = 0) -> str:
        wikitext = "".join(
            str(o)
            for o in (
                "  |",
                self.page.title(insite=site),
                "=",
                rank if (key == "rank") else getattr(self, key, ""),
            )
        )
        return wikitext


def iter_project_pages() -> Iterator[pywikibot.Page]:
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
        data = cast(Iterable[Tuple[int, bytes]], cur.fetchall())

    # XXX: Work around pywikibot bug T67262
    namespaces = {2: "User:", 4: "Wikipedia:", 12: "Help:"}

    progress = -1
    for i, (ns, title) in enumerate(data):
        percent = math.floor(i / rows * 100)
        if (percent > progress) and (percent % 5 == 0):
            logger.info(f"Analyzing pages: {percent}% complete")
            progress = percent
        yield pywikibot.Page(site, title=namespaces[ns] + str(title, encoding="utf-8"))

    logger.info("Analyzing pages: 100% complete")


def construct_table(data: Iterable[Essay], intro_r: str) -> str:
    logger.info("Constructing table")

    intro_t = Template(intro_r)
    intro = intro_t.substitute(
        date=datetime.utcnow().strftime("%H:%M, %d %B %Y (UTC)"), bot="AntiCompositeBot"
    )
    table = """
{| class="wikitable sortable plainlinks" style="width:100%; margin:auto"
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
            [intro, table],
            [essay.row(rank=i + 1) for i, essay in enumerate(data)],
            ["|}"],
        )
    )

    return table


def construct_data_page(data: Iterable[Essay]) -> str:
    keys = ["rank", "score"]
    key_line = "|%s={{#switch:{{{2|{{{page|}}}}}}"
    lines = itertools.chain(
        ["{{#switch:{{{1|{{{key|}}}}}}"],
        [
            list(
                itertools.chain(
                    [key_line % key],
                    [
                        essay.data_row(key=key, rank=i + 1)
                        for i, essay in enumerate(data)
                    ],
                    ["  }}"],
                )
            )
            for key in keys
        ],
        [
            f"|lastupdate = {datetime.utcnow().isoformat(timespec='minutes')}",
            "|¬ =",
            "|#default={{error|Key does not exist}}",
            "}}",
        ],
    )
    return "\n".join(lines)


def check_runpage() -> None:
    """Raises pywikibot.UserBlocked if on-wiki runpage is not True"""
    page = pywikibot.Page(site, "User:AntiCompositeBot/EssayImpact/Run")
    if not page.text.endswith("True"):
        raise pywikibot.UserBlocked("Runpage is false, quitting")


def write_table(text: str) -> None:
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


def load_wiki_config() -> Tuple[Dict[str, Union[int, float]], str]:
    page = pywikibot.Page(site, "User:AntiCompositeBot/EssayImpact/config.json")
    logger.info(f"Retrieving config from {page.title()}")
    data = json.loads(page.text)
    assert set(data["weights"].keys()).issubset({"watchers", "views", "links"})
    return data["weights"], data["intro"]


def main() -> None:
    logger.info("Starting up")
    check_runpage()
    weights, intro = load_wiki_config()

    data = []
    for page in iter_project_pages():
        essay = Essay(page)
        essay.calculate_score(weights)
        data.append(essay)

    data.sort(key=lambda e: e.score, reverse=True)
    table = construct_table(data, intro)

    if not simulate:
        check_runpage()
        write_table(table)
    else:
        print(table)
    logger.info("Finished")


if __name__ == "__main__":
    main()
