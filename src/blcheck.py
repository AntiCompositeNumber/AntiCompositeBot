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
import re
import itertools

enwiki = pywikibot.Site("en", "wikipedia")
metawiki = pywikibot.Site("meta", "meta")


def get_blacklist_regex():
    local = pywikibot.Page(enwiki, "MediaWiki:Spam-blacklist")
    meta = pywikibot.Page(metawiki, "Spam blacklist")

    blacklist = [
        line.partition("#")[0].replace(r"\x", r"\\x")
        for line in itertools.chain(local.text.split("\n"), meta.text.split("\n"))
        if line.partition("#")[0].strip()
    ]
    regex = r"".join([r"https?:\/\/[a-z0-9\-.]*(", r"|".join(blacklist), r")"])
    return re.compile(regex, flags=re.S | re.I)


def get_site_list():
    page = pywikibot.Page(enwiki, "User:Praxidicae/fntest")
    regex = re.compile(r"\*\{\{LinkSummary\|(.*)\}\}")
    for line in page.text:
        yield line, re.match(regex, line).group(1)


def check_site(regex, site):
    """Returns true if site is blacklisted"""
    return bool(re.search(regex, site)) if site else False


def struck(line):
    return f"*<s>{line[1:]}</s>"


def main():
    regex = get_blacklist_regex()
    sites = get_site_list()
    bl_sites = [(struck(line), site) for line, site in sites if check_site(regex, site)]
    bl_sites
