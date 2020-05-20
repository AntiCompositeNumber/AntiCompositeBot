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
import subprocess
import tempfile

enwiki = pywikibot.Site("en", "wikipedia")
metawiki = pywikibot.Site("meta", "meta")


def get_blacklist_regex():
    local = pywikibot.Page(enwiki, "MediaWiki:Spam-blacklist")
    meta = pywikibot.Page(metawiki, "Spam blacklist")

    blacklist = [
        line.partition("#")[0].replace("/", r"\/")
        for line in itertools.chain(local.text.split("\n"), meta.text.split("\n"))
        if line.partition("#")[0].strip()
    ]
    regex = r"".join([r"/https?:\/\/[a-z0-9\-.]*(", r"|".join(blacklist), r")/Si"])
    return regex


def get_site_list(page):
    regex = re.compile(r"\*\{\{LinkSummary\|(.*)\}\}")
    for line in page.text:
        match = re.match(regex, line)
        if match:
            yield line, match.group(1)


def run_grep(regex, sites):
    site_text = "\n".join(site[1] for site in sites)
    with tempfile.NamedTemporaryFile(delete=False, mode="w") as f:
        f.write(site_text)
        temp = f.name
    res = subprocess.run(
        ["grep", "-Po", "-ef", "-", "-f", temp],
        input="regex",
        capture_output=True,
        text=True,
        check=True,
    )
    return set(res.stdout.split("\n"))


def struck(line):
    return f"*<s>{line[1:]}</s>"


def update_text(page, new_lines):
    text = page.text
    for line, new_line in new_lines:
        text.replace(line, new_line)
    return text


def main():
    regex = get_blacklist_regex()
    page = pywikibot.Page(enwiki, "User:Praxidicae/fntest")
    sites = get_site_list(page)
    bl_sites = run_grep(regex, sites)
    new_lines = [(line, struck(line)) for line, site in sites if site in bl_sites]
    print(new_lines)
