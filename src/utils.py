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
import logging
import time
from typing import Callable, Any

logger = logging.getLogger(__name__)


def check_runpage(site: pywikibot.Site, task: str) -> None:
    """Raises pywikibot.UserBlocked if on-wiki runpage is not True"""
    page = pywikibot.Page(site, f"User:AntiCompositeBot/{task}/Run")
    if not page.text.endswith("True"):
        raise pywikibot.UserBlocked("Runpage is false, quitting")


def save_page(
    text: str, page: pywikibot.Page, summary: str, bot: bool = True, minor: bool = False
) -> None:
    logger.info(f"Saving to {page.title()}")
    if not text:
        raise pywikibot.PageNotSaved(
            page, message="New page text is blank, page %s was not saved"
        )
    elif page.text == text:
        raise pywikibot.PageNotSaved(
            page, message="Page text did not change, page %s was not saved"
        )
    else:
        page.text = text
        page.save(
            summary=summary,
            minor=minor,
            botflag=bot,
            quiet=True,
        )
        logger.info(f"Page {page.title(as_link=True)} saved")


def retry(function: Callable, retries: int, *args, **kwargs) -> Any:
    for i in range(retries):
        try:
            out = function(*args, **kwargs)
        except Exception as e:
            err = e
        else:
            break
    else:
        raise err
    return out


class Throttle:
    def __init__(self, delay: int):
        self.delay = delay
        self.last_edit = 0

    def throttle(self):
        now = time.monotonic()
        diff = round(self.delay - (now - self.last_edit), 2)
        if diff > 0:
            logger.debug(f"Sleeping for {diff} seconds")
            time.sleep(diff)
        self.last_edit = time.monotonic()
