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

import pytest
import unittest.mock as mock
import os
import sys

sys.path.append(os.path.realpath(os.path.dirname(__file__) + "/.."))
os.environ["LOG_FILE"] = "stderr"
import harvcheck  # noqa: E402

session = harvcheck.session

test_cases = [
    ("Broken sfn.{{sfn|Last|1234}}", True),
    ('Broken reused tag<ref name="foo" />', False),
    ('Broken named tag<ref name="foo">{{Harvnb|Author|4567}}</ref>', True),
    ("== Section ==\nBroken sfn.{{sfn|Last|1234}}", True),
    ("Working tag<ref>{{Harv|Real|1970}}</ref>", False),
    ("Broken tag with more text<ref>True fact {{Harvnb|Author|4567}}</ref>", True),
    ("Known issue{{sfn|Dead|Gone}}{{citation not found}}", False),
    ("Another broken reuse{{r|foo}}", False),
    ("Bare link, because why not[[#CITEREFDoesn'tExist]]", True),
    ("<onlyinclude>Inside an onlyinclude tag{{sfn|name|7777}}</onlyinclude>", True),
    (
        "<onlyinclude>Known inside an onlyinclude tag"
        "{{sfn|Gone|Dead}}{{citation not found}}</onlyinclude>",
        False,
    ),
    ("No quotes<ref name=bar>{{harvcol|Ghost Rider|2313}}</ref>", True),
]
footer = (
    "\n== References ==\n{{reflist}}\n"
    "* {{cite book|title=Reliable Source|last=Real|year=1970|ref=harv}}"
)


def wikitext_to_html(wikitext):
    url = (
        "https://en.wikipedia.org/api/rest_v1/transform/wikitext/to/html/"
        "User%3AAntiCompositeBot%2FHarvCheck%2Ftestcases"
    )
    data = {"wikitext": wikitext, "stash": True}
    resp = session.post(url, json=data)
    html = resp.text
    etag = resp.headers["etag"]
    return html, etag


def check_wikitext(input_wikitext):
    title = "User:AntiCompositeBot/HarvCheck/testcases"
    page = mock.Mock(text=input_wikitext)
    page.title.return_value = title
    mock_html = mock.Mock(return_value=wikitext_to_html(input_wikitext))
    mock_save = mock.Mock(return_value=None)

    with mock.patch("harvcheck.get_html", mock_html):
        with mock.patch("harvcheck.save_page", mock_save):
            harvcheck.main(page=page)

    mock_save.assert_called_once()
    new_wikitext = mock_save.call_args[0][1]
    return new_wikitext


@pytest.mark.parametrize("input_wikitext,expected", test_cases)
def test_wikitext_cases(input_wikitext, expected):
    input_wikitext += footer
    new_wikitext = check_wikitext(input_wikitext)
    assert (new_wikitext != input_wikitext) is expected
    if expected:
        assert "subst:broken footnote" in new_wikitext


def test_combined_wikitext():
    input_wikitext = ""
    for line in test_cases:
        input_wikitext += line[0] + "\n\n"

    input_wikitext += footer

    new_wikitext = check_wikitext(input_wikitext)
    new_wikitext_lines = new_wikitext.split("\n\n")[:-1]
    for new_line, (old_line, expected) in zip(new_wikitext_lines, test_cases):
        assert (new_line != old_line) is expected
