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
import datetime
import acnutils as utils
import argparse
import string
import json
import collections
from typing import Tuple, Iterator, Optional, cast, Deque

__version__ = "1.9"

logger = utils.getInitLogger("nolicense", level="INFO")

site = pywikibot.Site("commons", "commons")
cluster = "web"
simulate = None


def get_config():
    page = pywikibot.Page(site, "User:AntiCompositeBot/NoLicense/Config.json")
    conf_json = json.loads(page.text)
    logger.info(f"Loaded config from {page.title(as_link=True)}")
    logger.debug(conf_json)
    return conf_json


def iter_files_and_users(
    days, delay_mins=30
) -> Iterator[Tuple[pywikibot.Page, pywikibot.Page]]:
    start_ts = (
        (datetime.datetime.utcnow() - datetime.timedelta(days=days))
        .replace(hour=0, minute=0, second=0)
        .strftime("%Y%m%d%H%M%S")
    )
    end_ts = (
        datetime.datetime.utcnow() - datetime.timedelta(minutes=delay_mins)
    ).strftime("%Y%m%d%H%M%S")
    query = """
SELECT
  p0.page_namespace,
  p0.page_title,
  CONCAT("User talk:", actor_name)
FROM
  categorylinks
  JOIN page p0 ON cl_from = p0.page_id
  JOIN logging_logindex
    ON log_page = p0.page_id AND log_type = "upload"
  JOIN actor_logging ON log_actor = actor_id
WHERE
  cl_to = "Files_with_no_machine-readable_license"
  AND log_timestamp > %(start_ts) s
  AND log_timestamp < %(end_ts) s
  AND "Deletion_template_tag" NOT IN (
    SELECT lt_title
    FROM templatelinks
    JOIN linktarget ON lt_id = tl_target_id
    WHERE
      lt_namespace = 10
      AND tl_from = p0.page_id
  )
  AND (
    log_action = "upload"
    OR actor_id IN (
      SELECT log_actor
      FROM logging_logindex
      WHERE
        log_page = p0.page_id
        AND log_type = "upload"
        AND log_action = "upload"
    )
  )
GROUP BY page_id
ORDER BY actor_id
"""
    conn = toolforge.connect("commonswiki_p", cluster=cluster)
    with conn.cursor() as cur:
        cur.execute(query, args={"start_ts": start_ts, "end_ts": end_ts})
        data = cast(Iterator[Tuple[int, bytes, bytes]], cur.fetchall())
    for ns, title, user in data:
        page = pywikibot.Page(site, title=str(title, encoding="utf-8"), ns=ns)
        user_talk = pywikibot.Page(site, title=str(user, encoding="utf-8"))
        if not page.exists():
            continue
        if user_talk.isRedirectPage():
            user_talk = user_talk.getRedirectTarget()
        yield (
            page,
            user_talk,
        )


def check_templates(page: pywikibot.Page) -> bool:
    """Returns true if page has no license tag and is not tagged for deletion"""
    default_skip = ["Template:Deletion_template_tag", "Template:License template tag"]
    templates = {
        pywikibot.Page(site, title)
        for title in config.get("skip_templates", default_skip)
    }
    assert len(templates) >= 2
    page_templates = set(page.itertemplates())
    return page_templates.isdisjoint(templates)


def tag_page(page: pywikibot.Page, throttle: Optional[utils.Throttle] = None) -> bool:
    tag = config["tag_text"]
    summary_template = config["tag_summary"]
    summary = string.Template(summary_template).safe_substitute(version=__version__)
    return edit_page(page, tag, summary, throttle=throttle, mode="prepend")


def warn_user(
    user_talk: pywikibot.Page,
    queue: Deque[pywikibot.Page],
    throttle: Optional[utils.Throttle] = None,
) -> Deque:
    logger.info(f"Processing warning queue for {user_talk.title()}: {len(queue)} pages")
    logger.debug(str(queue))
    if len(queue) == 0:
        return queue
    elif len(queue) > 1 and not config["group_warnings"]:
        raise IndexError(
            "Grouped warnings are disabled but warn_user() "
            f"was called with {len(queue)} pages"
        )
    filepage = queue.popleft()
    also = ""
    if len(queue) > 0:
        also = config["warn_also"]
        also_line = string.Template(config["warn_also_line"])
        for page in queue.copy():
            also += also_line.safe_substitute(
                link=page.title(as_link=True, textlink=True, insite=site)
            )
            queue.remove(page)

    tag_template = string.Template(config["warn_text"])
    tag = tag_template.safe_substitute(title=filepage.title(), also=also)
    summary_template = config["warn_summary"]
    summary = string.Template(summary_template).safe_substitute(version=__version__)
    edit_page(
        user_talk,
        tag,
        summary,
        throttle=throttle,
        mode="append",
        force=True,
        new_ok=True,
    )
    return queue


def edit_page(
    page: pywikibot.Page,
    text: str,
    summary: str,
    throttle: Optional[utils.Throttle] = None,
    retries: int = 3,
    mode: str = "replace",
    force: bool = False,
    new_ok=False,
) -> bool:
    if throttle is not None:
        throttle.throttle()
    if simulate:
        logger.debug(f"Simulating {page.title()}")
        logger.debug(f"Summary: {summary}")
        logger.debug(f"New text ({mode}):\n{text}")
        return True
    utils.check_runpage(site, "NoLicense")
    try:
        utils.retry(
            utils.save_page,
            retries,
            page=page,
            text=text,
            mode=mode,
            summary=summary,
            bot=False,
            minor=False,
            force=force,
            new_ok=new_ok,
        )
    except Exception as err:
        logger.exception(err)
        return False
    else:
        return True


def main(limit: int = 0, days: int = 30) -> None:
    logger.info(f"NoLicense {__version__} starting up")
    utils.check_runpage(site, "NoLicense")
    throttle = utils.Throttle(config["edit_rate"])

    total = 0
    current_user = None
    queue: Deque[pywikibot.Page] = collections.deque()
    replag = utils.get_replag("commonswiki_p", cluster=cluster)
    if replag > datetime.timedelta(minutes=30):
        logger.warn(f"Replag is high ({str(replag)})")
    try:
        for page, user in iter_files_and_users(days):
            logger.info(f"{page.title()}: File {total + 1} of {limit}")
            if current_user is None:
                current_user = user
            elif user != current_user or not config["group_warnings"]:
                queue = warn_user(current_user, queue)
                current_user = user
            if limit and total >= limit:
                logger.info(f"Limit of {limit} pages reached")
                break
            if not page.botMayEdit():
                logger.info(f"Bot may not edit {page.title()}")
            elif page.title() in config.get("skip_files", []):
                logger.info("Page is on skip list, skipping.")
                continue
            elif check_templates(page) and tag_page(page, throttle=throttle):
                queue.append(page)
                total += 1
            else:
                logger.info("Page not tagged")
        else:
            logger.info("No more files to check")
    finally:
        if len(queue) > 0:
            warn_user(current_user, queue)

        logger.info(f"Shutting down, {total} files tagged")


config = get_config()
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--days",
        type=int,
        help="Files uploaded in the last DAYS days",
        default=config.get("max_age", 30),
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum pages to edit, 0 is no limit",
        default=config.get("batch_size", 10),
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Simulate operation, do not edit",
        default=config.get("simulate", False),
    )
    args = parser.parse_args()
    simulate = args.simulate
    try:
        main(limit=args.limit, days=args.days)
    except Exception as err:
        logger.exception(err)
        raise err
