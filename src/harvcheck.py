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

from mwparserfromhell.wikicode import Wikicode  # type: ignore
from bs4.element import Tag  # type: ignore
from pywikibot.page import BasePage  # type: ignore
from typing import Dict, List, Set, Any, Optional, Tuple, overload

session = requests.Session()
session.headers.update(
    {
        "User-Agent": (
            "anticompositetools harvcheck (dev), contact User:AntiCompositeNumber"
        )
    }
)
site = pywikibot.Site("en", "wikipedia")
simulate = True


def get_html(title: str, revision: str = "") -> Tuple[str, str]:
    url = "https://en.wikipedia.org/api/rest_v1/page/html/" + "/".join(
        urllib.parse.quote(i.replace(" ", "_"), safe="") for i in (title, revision) if i
    )
    resp = session.get(url)
    raw_html = resp.text
    etag = resp.headers["ETag"]
    return raw_html, etag


def parse_citeref_ids(soup: BeautifulSoup) -> Set[str]:
    ids = set()
    for element in soup.find_all(class_="citation"):
        el_id = element["id"]
        if el_id and el_id.startswith("CITEREF"):
            ids.add(el_id)

    return ids


def parse_citeref_links(title: str, soup: BeautifulSoup) -> Dict[str, List[Tag]]:
    """The inline footnote boxes have "cite_ref" ids and link to "cite_note" ids.
    The reference list items have "cite_note" ids and link to "cite_ref" ids.
    sfn inline boxes link to cite_note-FOOTNOTE ids
    Harvard citations link to CITENOTE ids
    ref=harv references have CITENOTE ids
    """
    links: Dict[str, List[Tag]] = {}
    for link in soup.find_all("a"):
        link_page, sep, fragment = link.get("href").partition("#")
        if link_page.endswith(title) and sep and fragment.startswith("CITEREF"):
            links.setdefault(fragment, []).append(link)

    return links


def parse_refs(title: str, soup: BeautifulSoup) -> Dict[str, List[Tag]]:
    refs: Dict[str, List[Tag]] = {}
    for ref in soup.find_all(class_="mw-ref"):
        link_page, sep, fragment = ref.find("a").get("href").partition("#")
        if link_page.endswith(title) and sep and fragment.startswith("cite_note"):
            refs.setdefault(fragment, []).append(ref)

    return refs


def find_mismatch(ids: Set[str], links: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in links.items() if key not in ids}


def find_note_id(element: Tag) -> str:
    note_id = element.parent.parent["id"]
    return note_id


def find_ref_for_note(note: Tag, page_refs: Dict[str, Any]) -> Any:
    note_id = find_note_id(note)
    ref = page_refs.get(note_id)
    return ref


def find_wikitext_for_ref(ref: Tag, note: Tag, title: str, etag: str) -> str:
    wikitext = html_to_wikitext(str(ref), title, etag)
    if not wikitext:
        raw_wikitext = html_to_wikitext(str(ref) + str(note.parent), title, etag)
        wikitext = "".join(raw_wikitext.partition("</ref>")[0:2])

    return wikitext


def html_to_wikitext(html: str, title: str, etag: str) -> str:
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
    tag = "{{subst:broken footnote}}"
    skip_tags = ["subst:broken footnote", "Broken footnote", "citation not found"]

    if target.startswith("<"):
        matches = wikitext.filter_tags(matches=target)
    elif target.startswith("{{"):
        matches = wikitext.filter_templates(matches=target)

    for obj in matches:
        index = wikitext.index(obj)
        try:
            next_obj = wikitext.nodes[index + 1]
            skip = next_obj.name.matches(skip_tags)
        except (AttributeError, IndexError):
            skip = False

        skip = str(obj) != target

        if not skip:
            wikitext.insert_after(obj, tag)

    return wikitext


def broken_anchors(title: str, revision: str = "") -> Dict[str, Set[str]]:
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
                ):
                    # skip self-closed ref tags, ref text defined elsewhere
                    continue
                broken_harvs.setdefault(link_id, set()).add(ref_wikitext)

    return broken_harvs


def save_page(page: BasePage, wikitext: str, summary: str) -> None:
    if not wikitext:
        raise ValueError
    page.text = wikitext

    check_runpage()
    if simulate:
        print(page.title(), summary)
        print(page.text)
    else:
        page.save(summary=summary)


def check_runpage() -> None:
    # TODO: actually implement
    pass


@overload
def main(title: None, page: BasePage) -> None:
    ...


@overload
def main(title: str, page: None) -> None:
    ...


def main(title: Optional[str] = None, page: Optional[BasePage] = None) -> None:
    assert page or title

    if page and not title:
        title = page.title()
    elif title and not page:
        page = pywikibot.Page(site, title)
    elif page and title:
        if page.title() != title:
            raise ValueError("Specified title and page do not match")

    assert page and title
    check_runpage()
    wikitext = mwph.parse(page.text)

    broken_harvs = broken_anchors(title)

    for link_id, ref_text_list in broken_harvs.items():
        for ref_wikitext in ref_text_list:
            wikitext = append_tags(wikitext, ref_wikitext)

    save_page(page, str(wikitext), "")


def auto():
    check_runpage()
    for page in site.allpages():
        main(page=page)
