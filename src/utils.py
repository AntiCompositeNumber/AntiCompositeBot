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
import logging.handlers
import time
import os
import datetime
import toolforge

from typing import Callable, Any, Dict

logger = logging.getLogger(__name__)


def logger_config(module: str, level: str = "INFO", filename: str = "") -> Dict:
    loglevel = os.environ.get("LOG_LEVEL", level)
    if loglevel == "VERBOSE":
        module_level = "DEBUG"
        root_level = "INFO"
    else:
        module_level = loglevel
        root_level = loglevel

    if os.environ.get("LOG_FILE"):
        _filename = os.environ["LOG_FILE"]
    elif filename:
        _filename = filename
    else:
        _filename = f"{module}.log"

    conf: Dict = {
        "version": 1,
        "formatters": {
            "log": {
                "format": "%(asctime)s %(name)s %(levelname)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
        "handlers": {},
        "loggers": {"pywiki": {"level": root_level}, module: {"level": module_level}},
        "root": {"level": root_level},
    }
    if _filename == "stderr":
        conf["handlers"]["console"] = {
            "class": "logging.StreamHandler",
            "formatter": "log",
        }
        conf["root"].setdefault("handlers", []).append("console")
    elif on_toolforge():
        conf["handlers"]["file"] = {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": get_log_location(_filename),
            "when": "D",
            "interval": 30,
            "backupCount": 3,
            "formatter": "log",
        }
        conf["root"].setdefault("handlers", []).append("file")
    else:
        conf["handlers"]["file"] = {
            "class": "logging.FileHandler",
            "filename": get_log_location(_filename),
            "formatter": "log",
        }
        conf["root"].setdefault("handlers", []).append("file")
    if os.environ.get("LOG_SMTP"):
        conf["handlers"]["smtp"] = {
            "class": "logging.handlers.SMTPHandler",
            "mailhost": "mail.tools.wmflabs.org",
            "fromaddr": "tools.anticompositebot@tools.wmflabs.org",
            "toaddrs": ["tools.anticompositebot@tools.wmflabs.org"],
            "subject": f"AntiCompositeBot {module} error",
            "level": "ERROR",
            "formatter": "log",
        }
        conf["root"].setdefault("handlers", []).append("smtp")

    return conf


def get_log_location(filename: str) -> str:
    """Returns a log location depending on system

    On Toolforge, uses $HOME/logs, creating if needed.
    If $HOME is not set or the bot is not running on Toolforge,
    the current directiory is used instead.

    Absolute paths (starting with "/") are returned without modification.
    """
    if filename.startswith("/"):
        return filename
    if on_toolforge() and os.environ.get("HOME"):
        logdir = os.path.join(os.environ["HOME"], "logs")
        try:
            os.mkdir(logdir)
        except FileExistsError:
            pass
    else:
        logdir = os.getcwd()

    return os.path.join(logdir, filename)


def on_toolforge() -> bool:
    """Detects if this is a Wikimedia Cloud Services environment.

    While this function is on_toolforge, it will also detect Cloud VPS
    """
    try:
        f = open("/etc/wmcs-project")
    except FileNotFoundError:
        wmcs = False
    else:
        wmcs = True
        f.close()
    return wmcs


def check_runpage(site: pywikibot.Site, task: str, override: bool = False) -> None:
    """Raises pywikibot.UserBlocked if on-wiki runpage is not True"""
    page = pywikibot.Page(site, f"User:AntiCompositeBot/{task}/Run")
    if not page.text.endswith("True") and not override:
        raise pywikibot.UserBlocked("Runpage is false, quitting")


def save_page(
    text: str,
    page: pywikibot.Page,
    summary: str,
    bot: bool = True,
    minor: bool = False,
    mode: str = "replace",
    force: bool = False,
    new_ok: bool = False,
    no_change_ok: bool = False,
) -> None:
    logger.info(f"Saving to {page.title()}")
    if not text:
        raise pywikibot.PageNotSaved(
            page, message="New page text is blank, page %s was not saved"
        )

    if mode == "replace":
        text = text
    elif mode == "append":
        try:
            text = page.get(force=True) + text
        except pywikibot.exceptions.NoPage as err:
            logger.exception(err)
            if new_ok:
                text = text
            else:
                raise
    elif mode == "prepend":
        try:
            text = text + page.get(force=True)
        except pywikibot.exceptions.NoPage as err:
            logger.exception(err)
            if new_ok:
                text = text
            else:
                raise
    else:
        raise ValueError("mode must be 'replace', 'append', or 'prepend', not {mode}")

    if page.get(force=True) == text:
        if not no_change_ok:
            raise pywikibot.PageNotSaved(
                page, message="Page text did not change, page %s was not saved"
            )
    else:
        page.text = text
        page.save(
            summary=summary, minor=minor, botflag=bot, quiet=True, force=force,
        )
        logger.info(f"Page {page.title(as_link=True)} saved")


def retry(function: Callable, retries: int, *args, **kwargs) -> Any:
    if retries < 1:
        raise IndexError("Retry called with retries < 1")
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


def get_replag(shard: str, cluster: str = "web") -> datetime.timedelta:
    conn = toolforge.connect("meta", cluster=cluster)
    with conn.cursor() as cur:
        count = cur.execute(
            "SELECT lag FROM heartbeat_p.heartbeat where shard = %s", [shard]
        )
        if count:
            return datetime.timedelta(seconds=float(cur.fetchall()[0][0]))
        else:
            raise ValueError
