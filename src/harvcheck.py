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
import pywikibot.pagegenerators  # type: ignore
import mwparserfromhell as mwph  # type: ignore
import json
import os
import toolforge
import argparse
import time
import logging
import re

from mwparserfromhell.wikicode import Wikicode  # type: ignore
from bs4.element import Tag  # type: ignore
from pywikibot.page import BasePage  # type: ignore
from typing import Dict, List, Set, Any, Optional, Tuple

__version__ = "0.6"

_conf_dir = os.path.realpath(os.path.dirname(__file__) + "/..")
logging.basicConfig(
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
    level=logging.INFO,
    filename=os.path.join(_conf_dir, "harvcheck.log"),
)
# shut pywikibot up
logging.getLogger("pywiki").setLevel(logging.INFO)

logger = logging.getLogger("harvcheck" if __name__ == "__main__" else __name__)
logger.setLevel(logging.DEBUG)

# load config
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
            "useragent", "harvcheck" + toolforge.set_user_agent(config["tool"])
        )
    }
)
# check if on toolforge
try:
    f = open("/etc/wmcs-project")
except FileNotFoundError:
    wmcs = False
else:
    wmcs = True
    f.close()

site = pywikibot.Site("en", "wikipedia")
last_edit = float()


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
        link_page, sep, fragment = link.get("href", "").partition("#")
        if link_page.endswith(title) and sep and fragment.startswith("CITEREF"):
            links.setdefault(fragment, []).append(link)

    return links


def parse_refs(title: str, soup: BeautifulSoup) -> Dict[str, List[Tag]]:
    """Parse Parsoid HTML for reflist citations
    Returns a dict of fragments and HTML citations
    """
    refs: Dict[str, List[Tag]] = {}
    for ref in soup.find_all(class_="mw-ref"):
        link_page, sep, fragment = ref.find("a").get("href", "").partition("#")
        if link_page.endswith(title) and sep and fragment.startswith("cite_note"):
            refs.setdefault(fragment, []).append(ref)

    return refs


def find_mismatch(ids: Set[str], links: Dict[str, Any]) -> Dict[str, Any]:
    """Returns dict of links where links are all in ids"""
    return {key: value for key, value in links.items() if key not in ids}


def find_note_id(element: Tag) -> str:
    """Finds the HTML ID for a citation"""
    note_id = element.parent.parent.get("id", "")
    return note_id


def find_ref_for_note(note: Tag, page_refs: Dict[str, Any]) -> Any:
    """Finds the corresponding [1] refs for the reflist note"""
    if "mw-reference-text" not in note.parent.get("class", [""]):
        return [note]
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


def index_nodes(wikitext, obj):
    try:
        index = wikitext.index(obj)
    except ValueError:
        # obj is inside something
        parent = wikitext.get_parent(obj)
        if isinstance(parent, mwph.nodes.tag.Tag):
            if str(parent.tag) == "ref":
                index, nodes, ret_obj = index_nodes(wikitext, parent)
            else:
                ret_obj = obj
                index = parent.contents.index(obj)
                nodes = parent.contents.nodes
    else:
        ret_obj = obj
        nodes = wikitext.nodes

    return index, nodes, ret_obj


def append_tags(wikitext: Wikicode, target: str) -> Wikicode:
    """Appends a tag for occurances of target in wikitext"""
    tag = config["tag"]
    skip_tags = config["skip_tags"]

    def match(n):
        return n == target

    if target.startswith("<"):
        matches = wikitext.filter_tags(matches=match)
    elif target.startswith("{{"):
        matches = wikitext.filter_templates(matches=match)
    else:
        matches = wikitext.filter(matches=match)

    for raw_obj in matches:
        index, nodes, obj = index_nodes(wikitext, raw_obj)
        try:
            # skip if there's already an inline maint tag
            next_obj = nodes[index + 1]
            skip = next_obj.name.matches(skip_tags)
        except (AttributeError, IndexError):
            # assume that it's the end of a section or something and tag anyway
            skip = False

        # make sure this is the right object unless we changed it already
        skip = skip or (str(obj) != target and str(obj) == str(raw_obj))

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
        throttle()
        page.save(summary=summary)


def check_runpage() -> None:
    """Raises pywikibot.UserBlocked if on-wiki runpage is not True"""
    page = pywikibot.Page(site, config["runpage"])
    if not page.text.endswith("True"):
        raise pywikibot.UserBlocked("Runpage is false, quitting")


def main(title: Optional[str] = None, page: Optional[BasePage] = None) -> bool:
    """Checks one page, returns True if problems found"""
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

    changes = len(broken_harvs)

    if (not broken_harvs) or (wikitext == page.text):
        return False
    else:
        save_page(
            page,
            str(wikitext),
            config["summary"].format(version=__version__, changes=changes),
        )
        return True


def throttle() -> None:
    """Prevents edits from happening faster than configured"""
    global last_edit
    now = time.monotonic()
    length = now - last_edit
    rate = config["rate"]
    if length < rate:
        logger.info(f"Throttling for {round(rate - length,1)} seconds")
        time.sleep(rate - length)
    last_edit = time.monotonic()


def iter_json_lines_pages(filename):
    """Iterates pages from a json lines file with page_title and page_namespace"""
    with open(filename) as f:
        for line in f:
            data = json.loads(line)
            yield pywikibot.Page(
                site, title=data["page_title"], ns=data["page_namespace"]
            )


def query_quarry(url):
    """Gets a json lines file from a Quarry url and iterates pages from it"""
    urldata = url.split("/")
    if urldata[3] == "query":
        run_url = quarry_get_run_url(url)
    else:
        run_url = url
    logger.info(f"Getting JSON lines from {run_url}")
    req = session.get(run_url)
    req.raise_for_status()
    # json file can be big, write it to disk and remove from memory
    filename = _conf_dir + str(id(req)) + ".json-lines"
    with open(filename, "x") as f:
        f.write(req.text)
    del req
    try:
        for page in iter_json_lines_pages(filename):
            yield page
    finally:
        os.remove(filename)


def quarry_get_run_url(query_url):
    """Gets the Quarry runid from a Quarry query page"""
    query = session.get(query_url)
    query.raise_for_status()
    regex = r"(?<=\"qrun_id\": )\d*"
    match = re.search(regex, query.text)
    if match:
        run_id = match.group(0)
        return f"https://quarry.wmflabs.org/run/{run_id}/output/0/json-lines"
    else:
        raise ValueError("No Quarry run id found")


def auto(method, limit: int = 0, start: str = "!", url: str = ""):
    """Checks multiple pages"""
    logger.info("Starting up")
    try:
        check_runpage()
        if method == "alpha":
            iterpages = site.allpages(start=start, filterredir=False)
        elif method == "random":
            iterpages = site.randompages(namespaces=0, redirects=False)
        elif method == "quarry":
            iterpages = query_quarry(url if url else config["quarry_url"])
        else:
            raise KeyError("Generator is invalid")

        checked, edited = 0, 0
        for page in iterpages:
            checked += 1
            if limit and edited >= limit:
                break
            result = main(page=page)
            if result:
                edited += 1
    except Exception as err:
        logger.exception(err)
        raise err
    finally:
        logger.info(f"Finished! {checked} articles scanned, {edited} articles edited.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    runtype = parser.add_mutually_exclusive_group(required=True)
    dryrun = parser.add_mutually_exclusive_group()
    runtype.add_argument(
        "--auto",
        help="runs the bot continuously",
        action="store",
        nargs="?",
        const=config.get("auto_method"),
    )
    runtype.add_argument("--page", help="run the bot on this page only")
    parser.add_argument(
        "--limit",
        type=int,
        help="how many pages to edit",
        action="store",
        nargs="?",
        const=config.get("limit", 0),
        default=0,
    )
    parser.add_argument("--start", help="page to start iterating from", default="!")
    dryrun.add_argument(
        "--simulate", action="store_true", help="prevents bot from saving"
    )
    dryrun.add_argument(
        "--run", action="store_true", help="overrides config to force saving"
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--url", default="")
    args = parser.parse_args()
    if args.simulate:
        simulate = True
    elif args.run:
        simulate = False

    if args.auto:
        auto(args.auto, limit=args.limit, start=args.start, url=args.url)
    elif args.page:
        if main(title=args.page):
            print("Done")
        else:
            print("No change")
