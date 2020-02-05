#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: Apache-2.0
# python 3.5

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
import pywikibot.pagegenerators as pagegenerators
import re
import difflib

site = pywikibot.Site("en", "wikipedia")


def iter_pages(limit=0):
    query = (
        "SELECT"
        "    page_namespace,"
        "    page_title"
        "FROM"
        "    externallinks"
        "    JOIN page ON el_from = page_id"
        "WHERE"
        "    el_to LIKE 'http://rpc.ift.org.mx/rpc/%' OR"
        "    el_to LIKE 'https://rpc.ift.org.mx/rpc/%'"
    )

    for i, page in enumerate(pagegenerators.MySQLPageGenerator(query, site=site)):
        if not limit or i < limit:
            yield page


def do_text_replace(old_text):
    regex = r"https?:\/\/rpc.ift.org.mx\/rpc\/"
    repl = "https://rpc.ift.org.mx/vrpc/"
    return re.sub(regex, repl, old_text)


def save_page(page, new_text):
    d = difflib.Differ()
    diff = d.compare(page.text, new_text)
    print("".join(diff))


def main():
    for page in iter_pages():
        new_text = do_text_replace(page.text)
        save_page(page, new_text)
