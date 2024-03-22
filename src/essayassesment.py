#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2020 AntiCompositeNumber

import pywikibot  # type: ignore
import toolforge
import requests
import itertools
import math
import json
import acnutils as utils
from string import Template
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple, Iterator, Iterable, cast, Dict, Union

__version__ = "1.0"

logger = utils.getInitLogger(
    "essayassesment", level="VERBOSE", filename="essayimpact.log"
)

site = pywikibot.Site("en", "wikipedia")
session = requests.session()
session.headers.update({"User-Agent": toolforge.set_user_agent("anticompositebot")})
simulate = False


@dataclass
class Essay:
    page: pywikibot.Page
    links: Optional[int] = None
    watchers: Optional[int] = None
    views: Optional[int] = None
    score: Optional[float] = None

    def get_views_and_watchers(self) -> None:
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

    def get_page_links(self) -> None:
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

    # def get_count_authors(self) -> None:
    #     page = self.page
    #     query = """
    #     SELECT COUNT(rev_actor)
    #     FROM page
    #     JOIN revision_userindex ON page_id = rev_page
    #     WHERE page_title = %s and page_namespace = %s
    #     """
    #     conn = toolforge.connect("enwiki_p")
    #     with conn.cursor() as cur:
    #         cur.execute(
    #             query,
    #             (page.title(underscore=True, with_ns=False), page.namespace().id)
    #         )
    #         self.authors = cast(Tuple[Tuple[int]], cur.fetchall())[0][0]

    def calculate_score(
        self,
        weights: Dict[str, Union[int, float]] = {
            "watchers": 10,
            "views": 2,
            "links": 0.01,
        },
    ) -> None:
        if self.views is None or self.watchers is None:
            self.get_views_and_watchers()
        if self.links is None:
            self.get_page_links()
        assert (
            self.watchers is not None
            and self.views is not None
            and self.links is not None
        )

        self.score = round(
            float(self.watchers) * weights["watchers"]
            + float(self.views) * weights["views"]
            + float(self.links) * weights["links"],
            2,
        )

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
        if key == "rank":
            val = str(rank)
        else:
            val = getattr(self, key, "")
        return f"    |{self.page.title(insite=site)} = {val}"


def iter_project_pages() -> Iterator[pywikibot.Page]:
    query = """
        SELECT page_namespace - 1, page_title
        FROM templatelinks
        JOIN linktarget ON lt_id = tl_target_id
        JOIN page ON tl_from = page_id
        WHERE
            lt_title = "WikiProject_Essays"
            and lt_namespace = 10
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
    key_line = "  |%s={{#switch:{{{2|{{{page|}}}}}}"
    lines = list(
        itertools.chain(
            ["{{#switch:{{{1|{{{key|¬}}}}}}"],
            list(
                itertools.chain.from_iterable(
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
                )
            ),
            [
                f"  |lastupdate = {datetime.utcnow().isoformat(timespec='minutes')}",
                "  |¬ =",
                "  |#default = {{error|Key does not exist}}",
                "}}",
            ],
        )
    )
    return "\n".join(lines)


def write_table(text: str) -> None:
    page = pywikibot.Page(
        site, "Wikipedia:WikiProject Wikipedia essays/Assessment/Links"
    )
    utils.save_page(
        text=text,
        page=page,
        summary=f"Updating assesment table (Bot) (EssayImpact {__version__}",
        minor=False,
        bot=False,
    )


def write_data_page(text: str) -> None:
    page = pywikibot.Page(site, "User:AntiCompositeBot/EssayImpact/data")
    utils.save_page(
        text=text,
        page=page,
        summary=f"Updating assesment data (Bot) (EssayImpact {__version__}",
        minor=False,
        bot=False,
    )


def load_wiki_config() -> Tuple[Dict[str, Union[int, float]], str]:
    page = pywikibot.Page(site, "User:AntiCompositeBot/EssayImpact/config.json")
    logger.info(f"Retrieving config from {page.title()}")
    data = json.loads(page.text)
    assert set(data["weights"].keys()).issubset({"watchers", "views", "links"})
    return data["weights"], data["intro"]


def main() -> None:
    logger.info("Starting up")
    utils.check_runpage(site, task="EssayImpact")
    weights, intro = load_wiki_config()

    data = []
    for page in iter_project_pages():
        essay = Essay(page)
        essay.calculate_score(weights)
        data.append(essay)

    data.sort(key=lambda e: cast(float, e.score), reverse=True)
    table = construct_table(data, intro)
    datapage = construct_data_page(data)

    if not simulate:
        utils.check_runpage(site, task="EssayImpact")
        write_table(table)
        write_data_page(datapage)
    else:
        print(table)
    logger.info("Finished")


if __name__ == "__main__":
    main()
