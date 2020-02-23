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


from bs4 import BeautifulSoup  # type: ignore
import requests
import urllib.parse
import pywikibot  # type: ignore
import mwparserfromhell as mwph  # type: ignore
import json
import os
import toolforge
import argparse
import time
import logging

from mwparserfromhell.wikicode import Wikicode  # type: ignore
from bs4.element import Tag  # type: ignore
from pywikibot.page import BasePage  # type: ignore
from typing import Dict, List, Set, Any, Optional, Tuple

__version__ = "0.1"
logging.basicConfig(
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s", level=logging.INFO,
)
pwl = logging.getLogger("pywiki")
pwl.setLevel(logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# load config
_conf_dir = os.path.realpath(os.path.dirname(__file__) + "/..")
with open(os.path.join(_conf_dir, "default_config.json")) as f:
    config = json.load(f)["harvcheck"]
try:
    with open(os.path.join(_conf_dir, "config.json")) as f:
        config.update(json.load(f).get("harvcheck", {}))
except FileNotFoundError:
    pass

simulate = config.get("simulate", True)

session = requests.Session()
session.headers.update(
    {
        "User-Agent": config.get(
            "summary", "harvcheck" + toolforge.set_user_agent(config["tool"])
        )
    }
)
site = pywikibot.Site("en", "wikipedia")


def get_html(title: str, revision: str = "") -> Tuple[str, str]:
    """Get Parsoid HTML for a page (and optional revision)"""
    url = "https://en.wikipedia.org/api/rest_v1/page/html/" + "/".join(
        urllib.parse.quote(i.replace(" ", "_"), safe="") for i in (title, revision) if i
    )
    resp = session.get(url)
    raw_html = resp.text
    etag = resp.headers["ETag"]
    return raw_html, etag


def parse_citeref_ids(soup: BeautifulSoup) -> Set[str]:
    """Parse Parsoid HTML and return html ids for citations"""
    ids = set()
    for element in soup.find_all(class_="citation"):
        el_id = element.get("id")
        if el_id and el_id.startswith("CITEREF"):
            ids.add(el_id)

    return ids


def parse_citeref_links(title: str, soup: BeautifulSoup) -> Dict[str, List[Tag]]:
    """Parse Parsoid HTML for same-page CITEREF links
    Returns a dict of fragments and HTML a tags
    """
    # The inline footnote boxes have "cite_ref" ids and link to "cite_note" ids.
    # The reference list items have "cite_note" ids and link to "cite_ref" ids.
    # sfn inline boxes link to cite_note-FOOTNOTE ids
    # Harvard citations link to CITEREF ids
    # ref=harv references have CITEREF ids

    links: Dict[str, List[Tag]] = {}
    for link in soup.find_all("a"):
        link_page, sep, fragment = link.get("href").partition("#")
        if link_page.endswith(title) and sep and fragment.startswith("CITEREF"):
            links.setdefault(fragment, []).append(link)

    return links


def parse_refs(title: str, soup: BeautifulSoup) -> Dict[str, List[Tag]]:
    """Parse Parsoid HTML for reflist citations
    Returns a dict of fragments and HTML citations
    """
    refs: Dict[str, List[Tag]] = {}
    for ref in soup.find_all(class_="mw-ref"):
        link_page, sep, fragment = ref.find("a").get("href").partition("#")
        if link_page.endswith(title) and sep and fragment.startswith("cite_note"):
            refs.setdefault(fragment, []).append(ref)

    return refs


def find_mismatch(ids: Set[str], links: Dict[str, Any]) -> Dict[str, Any]:
    """Returns dict of links where links are all in ids"""
    return {key: value for key, value in links.items() if key not in ids}


def find_note_id(element: Tag) -> str:
    """Finds the HTML ID for a citation"""
    note_id = element.parent.parent["id"]
    return note_id


def find_ref_for_note(note: Tag, page_refs: Dict[str, Any]) -> Any:
    """Finds the corresponding [1] refs for the reflist note"""
    note_id = find_note_id(note)
    ref = page_refs.get(note_id)
    return ref


def find_wikitext_for_ref(ref: Tag, note: Tag, title: str, etag: str) -> str:
    wikitext = html_to_wikitext(str(ref), title, etag)
    # if the ref is a template, it gets returned
    if not wikitext:
        # if the ref is not a template, it must be a tag
        raw_wikitext = html_to_wikitext(str(ref) + str(note.parent), title, etag)
        wikitext = "".join(raw_wikitext.partition("</ref>")[0:2])

    return wikitext


def html_to_wikitext(html: str, title: str, etag: str) -> str:
    """Converts html to wikitext in a page and etag context using the Parsoid API"""
    url = (
        "https://en.wikipedia.org/api/rest_v1/transform/html/to/wikitext/"
        + urllib.parse.quote(title.replace(" ", "_"), safe="")
    )
    data = {"html": str(html), "scrub_wikitext": True}
    headers = {"if-match": etag}
    resp = session.post(url, json=data, headers=headers)
    wikitext = resp.text
    return wikitext


def append_tags(wikitext: Wikicode, target: str) -> Wikicode:
    """Appends a tag for occurances of target in wikitext"""
    tag = config["tag"]
    skip_tags = config["skip_tags"]

    if target.startswith("<"):
        matches = wikitext.filter_tags(matches=lambda n: n == target)
    elif target.startswith("{{"):
        matches = wikitext.filter_templates(matches=lambda n: n == target)

    for obj in matches:
        index = wikitext.index(obj)
        try:
            # skip if there's already an inline maint tag
            next_obj = wikitext.nodes[index + 1]
            skip = next_obj.name.matches(skip_tags)
        except (AttributeError, IndexError):
            # assume that it's the end of a section or something and tag anyway
            skip = False

        # make sure this is the right object
        skip = skip or str(obj) != target

        if not skip:
            wikitext.insert_after(obj, tag)

    return wikitext


def broken_anchors(title: str, revision: str = "") -> Dict[str, Set[str]]:
    """Returns a dict of broken anchors and the refs that contain them"""
    raw_html, etag = get_html(title, revision)
    soup = BeautifulSoup(raw_html, "html.parser")

    citeref_links = parse_citeref_links(title, soup)
    citeref_ids = parse_citeref_ids(soup)
    page_refs = parse_refs(title, soup)

    missing_link_notes = find_mismatch(citeref_ids, citeref_links)
    broken_harvs: Dict[str, Set[str]] = {}
    for link_id, notes in missing_link_notes.items():
        for note in notes:
            refs = find_ref_for_note(note, page_refs)
            for ref in refs:
                ref_wikitext = find_wikitext_for_ref(ref, note, title, etag)
                if (
                    ref_wikitext.endswith("/>")
                    and ref_wikitext.startswith("<ref")
                    and not ref_wikitext.startswith("<ref>")
                ) or (ref_wikitext.startswith("{{r")):
                    # skip self-closed ref tags, ref text defined elsewhere
                    continue
                broken_harvs.setdefault(link_id, set()).add(ref_wikitext)

    return broken_harvs


def save_page(page: BasePage, wikitext: str, summary: str) -> None:
    """Saves wikitext to the on-wiki page, unless simulate is set"""
    if not wikitext:
        raise ValueError
    if wikitext == page.text:
        return
    page.text = wikitext

    check_runpage()
    if simulate:
        print(page.title(), summary)
        print(page.text)
    else:
        page.save(summary=summary)


def check_runpage() -> None:
    """Raises pywikibot.UserBlocked if on-wiki runpage is not True"""
    page = pywikibot.Page(site, config["runpage"])
    if not page.text.endswith("True"):
        raise pywikibot.UserBlocked("Runpage is false, quitting")


def main(title: Optional[str] = None, page: Optional[BasePage] = None) -> bool:
    assert page or title

    if page and not title:
        title = page.title()
    elif title and not page:
        page = pywikibot.Page(site, title)
    elif page and title:
        if page.title() != title:
            raise ValueError("Specified title and page do not match")

    assert page and title
    logger.info(f"Checking {title}")
    check_runpage()
    wikitext = mwph.parse(page.text)

    broken_harvs = broken_anchors(title)

    for link_id, ref_text_list in broken_harvs.items():
        for ref_wikitext in ref_text_list:
            wikitext = append_tags(wikitext, ref_wikitext)

    if not broken_harvs or wikitext == page.text:
        return False
    else:
        save_page(page, str(wikitext), config["summary"])
        return True


def throttle(start_time: float) -> None:
    end_time = time.monotonic()
    length = end_time - start_time
    rate = config["rate"]
    if length < rate:
        logger.info(f"Throttling for {rate - length} seconds")
        time.sleep(rate - length)


def auto(limit: int = 0, start: str = "!"):
    logger.info("Starting up")
    check_runpage()
    i = 0
    for page in site.allpages(start=start, content=True, filterredir=False):
        start_time = time.monotonic()
        if limit and i >= limit:
            break
        result = main(page=page)
        if result:
            i += 1
            if i != limit:
                throttle(start_time)

    logger.info("Finished!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    runtype = parser.add_mutually_exclusive_group(required=True)
    runtype.add_argument(
        "--auto", help="runs the bot continuously", action="store_true"
    )
    runtype.add_argument("--page", help="run the bot on this page only")
    parser.add_argument("--limit", type=int, help="how many pages to edit", default=0)
    parser.add_argument("--start", help="page to start iterating from", default="!")
    parser.add_argument(
        "--simulate", action="store_true", help="prevents bot from saving"
    )
    args = parser.parse_args()
    if args.simulate:
        simulate = True
    if args.auto:
        auto(limit=args.limit, start=args.start)
    elif args.page:
        if main(title=args.page):
            print("Done")
        else:
            print("No change")
