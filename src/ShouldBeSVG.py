#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: Apache-2.0


# Copyright 2019 AntiCompositeNumber

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generates reports for highly-used images that should use vector graphics."""

import datetime
import argparse
import re
import json
import pywikibot  # type: ignore
import toolforge
import acnutils as utils
from pymysql.err import OperationalError
from pywikibot import pagegenerators
from typing import Dict, Iterator, NamedTuple, List, cast, Tuple

__version__ = "2.2"

logger = utils.getInitLogger("ShouldBeSVG", level="VERBOSE")


class FileUsage(NamedTuple):
    title: str
    usage: int

    def gallery_line(self, i: int) -> str:
        return f"{self.title}|{i}. Used {self.usage} times."


class UsageResult(NamedTuple):
    files: List[FileUsage]
    total: int
    skipped: List[str]


def get_usage(cat: pywikibot.Category, depth: int, total: int) -> UsageResult:
    try:
        usage = db_get_usage(cat, depth)
    except OperationalError:
        usage = api_get_usage(cat, depth, total)
    return usage


def db_get_usage(cat: pywikibot.Category, depth: int) -> UsageResult:
    query = """
SELECT page_title, count(*)
FROM categorylinks
JOIN page ON cl_from = page_id
LEFT JOIN globalimagelinks ON page_title = gil_to
JOIN image ON img_name = page_title
WHERE
    cl_to IN %(cats)s
    AND img_major_mime = "image"
    AND img_minor_mime != "svg+xml"
GROUP BY page_title
ORDER BY count(*) DESC
"""
    conn = toolforge.connect("commonswiki")
    with conn.cursor() as cur:
        total = cur.execute(
            query,
            args={
                "cats": [
                    cat.title(with_ns=False, underscore=True)
                    for cat in list_cats(cat, depth)
                ]
            },
        )
        data = cast(List[Tuple[bytes, int]], cur.fetchall())
    return UsageResult(
        [
            FileUsage(f"File:{str(page, encoding='utf-8')}", count)
            for page, count in data
        ][:200],
        total,
        [],
    )


def list_cats(cat: pywikibot.Category, depth: int) -> Iterator[pywikibot.Category]:
    yield cat
    if depth > 0:
        for subcat in cat.subcategories(recurse=depth - 1):
            yield subcat


def api_get_usage(cat: pywikibot.Category, depth: int, total: int) -> UsageResult:
    """Get usage information for every file in the supplied category"""
    gen = pagegenerators.CategorizedPageGenerator(
        cat, recurse=depth, namespaces=6, total=total
    )

    # Generate a dictionary with diagrams that should be SVG.
    usage_counts = []
    skipped = []

    for page in gen:
        page = pywikibot.FilePage(page)
        # First, grab the mimetype of the file.
        # If that's not possible, the file is broken and should be skipped.
        try:
            mimetype = page.latest_file_info.mime
        except (pywikibot.PageRelatedError, AttributeError):
            skipped.append(page.title())
            logger.info("Skipping", page)
        else:
            # The categories are a bit messy, so make sure the image isn't
            # already an SVG.
            if mimetype != "image/svg+xml":
                try:
                    usage = pywikibot.FilePage.globalusage(page)
                    usage_counts.append(FileUsage(page.title(), len(list(usage))))
                except (pywikibot.NoUsernameError, pywikibot.PageRelatedError):
                    # Pywikibot complains if the bot doesn't have an account
                    # on a wiki where a file is used. If that happens,
                    # skip the file.
                    skipped.append(page.title())
                    logger.info("Skipping", page)

    # Sort from greatest to least
    usage_counts_sorted = sorted(
        usage_counts, key=lambda file: file.usage, reverse=True
    )
    return UsageResult(usage_counts_sorted[:200], len(usage_counts), skipped)


def construct_gallery(cat: pywikibot.Category, usage: UsageResult, depth: int) -> str:
    """Take the output from get_usage() and turn it into a wikitext gallery"""
    date = datetime.date.today()
    cats = f"'''[[:{cat.title()}]]''' ({cat.categoryinfo['files']} files) \n"
    page_cats = f"{cat.aslink()}\n[[Category:Images that should use vector graphics]]"

    cats += "\n".join(
        [
            (
                f"* {subcat.title(as_link=True, textlink=True)} "
                f"({subcat.categoryinfo['files']} files)"
            )
            for subcat in list_cats(cat, depth)
        ][1:]
    )
    gallery_lines = "\n".join(
        image.gallery_line(i + 1) for i, image in enumerate(usage.files[:200])
    )

    # If any files were skipped, write an explanatory message and the files.
    skipped = usage.skipped
    if skipped:
        skipped_files = (
            "The following files were skipped due to errors "
            "during the generation of this report:\n"
        ) + "\n".join(f"* [[:{page.title()}]]" for page in skipped)
    else:
        skipped_files = ""

    # Now we construct the gallery itself. Everything is formatted by now,
    # it just needs to be slotted into the right spot.
    gallery = f"""\
Last update: {{{{ISODate|1={date}}}}}.

This report includes the following categories while counting only the usage \
of each file in the main namespace.

{cats}
Total number of scanned files: {usage.total}
<gallery showfilename=yes>
{gallery_lines}
</gallery>

This report was generated by AntiCompositeBot ShouldBeSVG {__version__}. {skipped_files}
{page_cats}"""
    return gallery


def save_page(target: pywikibot.Page, gallery: str) -> None:
    """Saves the page to Commons, making sure to leave text above the line"""
    old_wikitext = target.text
    regex = re.compile(
        "(?<=<!-- Only text ABOVE this line will be preserved on updates -->\n).*",
        re.M | re.S,
    )
    new_wikitext = re.sub(regex, gallery, old_wikitext)

    utils.retry(
        utils.save_page,
        2,
        text=new_wikitext,
        page=target,
        summary=f"Updating gallery (Bot) (#ShouldBeSVG {__version__})",
        bot=False,
        minor=True,
    )


def handle_args() -> argparse.Namespace:
    # Handle command line arguments. See ShouldBeSVG.py --help for details
    parser = argparse.ArgumentParser(
        description=("Generate global usage reports" "for vectorization categories.")
    )
    parser.add_argument("key")
    parser.add_argument(
        "--total", help="maximum number of files to scan", type=int, default=None
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="prints output to stdout instead of saving it",
    )
    parser.add_argument(
        "--run_override",
        action="store_true",
        help="force the bot to ignore the runpage",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args()


def find_report(key: str, times: Dict[str, str]) -> str:
    if key == "auto":
        dt = datetime.datetime.utcnow()
        now = dt.strftime("%u%H")
        try:
            return times[now]
        except KeyError:
            logger.error("Check your timing, there's no report to run this hour", now)
            raise

    return key


def main() -> None:
    args = handle_args()

    site = pywikibot.Site("commons", "commons")
    utils.check_runpage(site, task="ShouldBeSVG", override=args.run_override)

    logger.info("Starting up")

    # Download a dict relating keys to galleries, categories, and depth values.
    reports_conf = json.loads(
        pywikibot.Page(site, "User:AntiCompositeBot/ShouldBeSVG/reports.json").text
    )
    times = reports_conf["times"]
    key = find_report(args.key, times)
    report_conf = reports_conf["reports"][key]

    cat = pywikibot.Category(site, report_conf["category"])
    depth = report_conf["depth"]

    usage_result = get_usage(cat, depth, args.total)
    gallery = construct_gallery(cat, usage_result, depth)

    if args.simulate:
        logger.debug(gallery)
    else:
        save_page(pywikibot.Page(site, report_conf["gallery"]), gallery)

    logger.info("Finished")


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        logger.exception(err)
        raise err
