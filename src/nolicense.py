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
import datetime
import utils
import logging
import argparse
import string
import json
from typing import Tuple, Iterator, Optional

site = pywikibot.Site("commons", "commons")
logging.basicConfig(
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
    level=logging.INFO,
    # filename="nolicense.log",
)
logger = logging.getLogger("NoLicense")
logger.setLevel(logging.DEBUG)
simulate = True

__version__ = 0.1


def get_config():
    page = pywikibot.Page(site, "User:AntiCompositeBot/NoLicense/Config.json")
    conf_json = json.loads(page.text)
    logger.info(f"Loaded config from {page.title(as_link=True)}")
    logger.debug(conf_json)
    return conf_json


def iter_files_and_users(days) -> Iterator[Tuple[pywikibot.Page, pywikibot.Page]]:
    ts = (
        (datetime.datetime.utcnow() - datetime.timedelta(days=days))
        .replace(hour=0, minute=0, second=0)
        .strftime("%Y%m%d%H%M%S")
    )
    query = """
SELECT p0.page_namespace, p0.page_title, CONCAT("User talk:", actor_name)
FROM categorylinks
JOIN page p0 ON cl_from = p0.page_id
JOIN logging_logindex
    ON log_page = p0.page_id
    AND log_type = "upload"
    AND log_action = "upload"
JOIN actor_logging ON log_actor = actor_id
WHERE
    cl_to = "Files_with_no_machine-readable_license"
    AND log_timestamp > %(ts)s
    AND "Deletion_template_tag" NOT IN (
        SELECT tl_title
        FROM templatelinks
        WHERE tl_namespace = 10 AND tl_from = p0.page_id
    )"""
    conn = toolforge.connect("commonswiki_p")
    with conn.cursor() as cur:
        cur.execute(query, args={"ts": ts})
        data = cur.fetchall()
    for ns, title, user in data:
        yield (
            pywikibot.Page(site, title=str(title, encoding="utf-8"), ns=ns),
            pywikibot.Page(site, title=str(user, encoding="utf-8")),
        )


def check_templates(page: pywikibot.Page) -> bool:
    cats = set(page.categories())
    templates = set(page.itertemplates())
    return (
        pywikibot.Page(site, "Template:Deletion_template_tag") not in templates
    ) and (
        pywikibot.Category(site, "Category:Files_with_no_machine-readable_license")
        in cats
    )


def tag_page(page: pywikibot.Page, throttle: Optional[utils.Throttle] = None) -> bool:
    tag = config["tag_text"]
    text = tag + page.text
    summary = (
        "No license found, tagging with {{[[Template:No license since|]]}} "
        f"(Bot) (NoLicense {__version__})"
    )
    return edit_page(page, text, summary, throttle=throttle)


def warn_user(
    user_talk: pywikibot.Page,
    filepage: pywikibot.Page,
    throttle: Optional[utils.Throttle] = None,
) -> bool:
    tag_template = config["warn_text"]
    tag = string.Template(tag_template).substitute(title=filepage.title())
    text = user_talk.text + tag
    summary = (
        "Notifying about file tagged for deletion with no license "
        f"(Bot) (NoLicense {__version__})"
    )
    return edit_page(user_talk, text, summary, throttle=throttle)


def edit_page(
    page: pywikibot.Page,
    text: str,
    summary: str,
    throttle: Optional[utils.Throttle] = None,
) -> bool:
    if throttle is not None:
        throttle.throttle()
    if simulate:
        logger.debug(f"Simulating {page.title()}")
        logger.debug(f"Summary: {summary}")
        logger.debug(f"New text:\n{text}")
        return True
    utils.check_runpage(site, "NoLicense")
    try:
        utils.retry(
            utils.save_page,
            3,
            page=page,
            text=text,
            summary=summary,
            bot=False,
            minor=False,
        )
    except Exception as err:
        logger.exception(err)
        return False
    else:
        return True


def main(limit: int = 0, days: int = 30) -> None:
    logger.info(f"Starting up")
    utils.check_runpage(site, "NoLicense")
    throttle = utils.Throttle(config["edit_rate"])

    total = 0
    for page, user in iter_files_and_users(days):
        logger.debug(total)
        if limit and total >= limit:
            logger.info(f"Limit of {limit} pages reached")
            break
        elif check_templates(page) and tag_page(page, throttle=throttle):
            warn_user(user, page)
            total += 1
    else:
        logger.info(f"Queue is empty")
    logger.info(f"Shutting down, {total} files tagged")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--days", type=int, help="Files uploaded in the last DAYS days", default=30
    )
    parser.add_argument("--limit", type=int, help="Maximum pages to edit", default=0)
    parser.add_argument(
        "--simulate", action="store_true", help="Simulate operation, do not edit"
    )
    args = parser.parse_args()
    config = get_config()
    simulate = args.simulate or config.get("simulate", False)
    main(limit=args.limit, days=args.days)
