#!/usr/bin/env python3
# coding: utf-8

import pywikibot
import toolforge
import requests
import itertools
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

site = pywikibot.Site("en", "wikipedia")
session = requests.session()
session.headers.update({"User-Agent": toolforge.set_user_agent("anticompositebot")})


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
        cur.execute(query)
        data = cur.fetchall()

    for ns, title in data:
        yield pywikibot.Page(site, ns=ns, title=str(title, encoding="utf-8"))


def construct_table(data):
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


def main():
    data = []
    for page in iter_project_pages():
        essay = Essay(page)
        essay.calculate_score()
        data.append(essay)
    table = construct_table(data)
    print(table)


if __name__ == "__main__":
    main()
