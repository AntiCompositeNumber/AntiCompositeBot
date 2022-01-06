#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: Apache-2.0


# Copyright 2022 AntiCompositeNumber

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations
import pywikibot  # type: ignore
import acnutils
import dataclasses
import datetime
import json
import string

from typing import Literal, Optional

__version__ = "0.1"

logger = acnutils.getInitLogger("catcron", level="VERBOSE")
site = pywikibot.Site("commons", "commons")


@dataclasses.dataclass
class Target:
    """
    Information about a category to create

    :param schedule: How often to create a new category
    :param title: Title of the category to be created
    :param text: Text of the category page
    :param offset: How far in advance to create categories
    """

    schedule: Literal["daily", "monthly", "yearly"]
    title: string.Template
    text: string.Template
    offset: datetime.timedelta = datetime.timedelta(days=30)

    @classmethod
    def fromdict(cls, d: dict) -> Target:
        kwargs = dict(
            schedule=d["schedule"].lower(),
            title=string.Template(d["title"]),
            text=string.Template(d["text"]),
        )
        if "offset" in d:
            kwargs["offset"] = datetime.timedelta(days=d["offset"])

        return cls(**kwargs)

    def should_run(self, date: datetime.date) -> bool:
        if self.schedule == "yearly" and not (date.month == 1 and date.day == 1):
            return False
        elif self.schedule == "monthly" and not (date.day == 1):
            return False
        return True

    @staticmethod
    def format(template: string.Template, date: datetime.date) -> str:
        return template.safe_substitute(
            year=date.strftime("%Y"),
            month=date.strftime("%m"),
            month1=str(date.month),
            monthname=date.strftime("%B"),
            monthabbrev=date.strftime("%b"),
            day=str(date.day),
            day2=date.strftime("%d"),
            isodate=date.isoformat(),
        )

    def create(
        self, date: datetime.date, throttle: Optional[acnutils.Throttle] = None
    ) -> None:
        if not self.should_run(date):
            logger.debug(
                f"Skipping {self.title.template}, not on the schedule for {date.isoformat()}"
            )
            return

        real_title = self.format(self.title, date)
        if not real_title.startswith("Category:"):
            real_title = "Category:" + real_title

        page = pywikibot.Page(site, real_title)
        if page.exists():
            logger.debug(
                f"Skipping {self.title.template}, already exists {page.title(as_link=True)}"
            )
            return

        real_text = self.format(self.text, date)

        if throttle:
            throttle.throttle()
        acnutils.check_runpage(site, "CatCron")

        # logger.debug(real_title)
        # logger.debug(real_text)
        acnutils.save_page(
            text=real_text,
            page=page,
            summary=(
                "Creating daily/monthly maintenance categories "
                f"(CatCron {__version__})"
            ),
            bot=True,
            minor=False,
            mode="replace",
            new_ok=True,
        )


def get_config() -> dict:
    page = pywikibot.Page(site, "User:AntiCompositeBot/CatCron/config.json")
    conf_json = json.loads(page.text)
    logger.info(f"Loaded config from {page.title(as_link=True)}")
    logger.debug(conf_json)
    return conf_json


def main() -> None:
    logger.info(f"CatCron {__version__} starting up")
    config = get_config()
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    throttle = acnutils.Throttle(60)

    for target_dict in config["targets"]:
        target = Target.fromdict(target_dict)
        # double-check tomorrow's category has been created
        for date in [tomorrow, today + target.offset]:
            try:
                target.create(date, throttle)
            except acnutils.RunpageError:
                raise
            except Exception as err:
                logger.exception(err)

    logger.info("Finished")


if __name__ == "__main__":
    main()
