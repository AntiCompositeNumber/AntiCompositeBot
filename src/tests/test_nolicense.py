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

import os
import sys
import itertools
import collections
import datetime
import pywikibot
import pytest
import unittest.mock as mock

sys.path.append(os.path.realpath(os.path.dirname(__file__) + "/.."))
import nolicense  # noqa: E402
import utils  # noqa: E402

site = nolicense.site


def test_get_config():
    conf = nolicense.get_config()
    assert conf


def test_iter_fiels_and_users():
    mock_cursor = mock.MagicMock()
    mock_cursor.fetchall.return_value = [(6, b"Example.jpg", b"User talk:Example")]
    mock_conn = mock.MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    with mock.patch("toolforge.connect", return_value=mock_conn):
        assert list(nolicense.iter_files_and_users(30, 30)) == [
            (
                pywikibot.Page(nolicense.site, "File:Example.jpg"),
                pywikibot.Page(nolicense.site, "User talk:Example"),
            ),
        ]


@pytest.mark.parametrize(
    "pages,expected",
    [
        ([pywikibot.Page(site, "Template:Cc-by-sa-4.0")], False),
        ([pywikibot.Page(site, "Template:No license since")], False),
        (
            [
                pywikibot.Page(site, "Template:Cc-by-sa-4.0"),
                pywikibot.Page(site, "Template:No license since"),
            ],
            False,
        ),
        ([pywikibot.Page(site, "Template:Bots")], True),
    ],
)
def test_check_templates(pages, expected):
    templates = itertools.chain.from_iterable(p.itertemplates() for p in pages)
    page = mock.MagicMock(spec=pywikibot.Page)
    page.itertemplates = mock.MagicMock(return_value=templates)
    assert nolicense.check_templates(page) is expected


def test_edit_page():
    """(
    page: pywikibot.Page,
    text: str,
    summary: str,
    throttle: Optional[utils.Throttle] = None,
    )"""
    throttle_throttle = mock.Mock()
    throttle = mock.Mock(throttle=throttle_throttle)
    with mock.patch("utils.save_page") as save_page:
        page = mock.Mock(spec=pywikibot.Page, text="foo")
        page.get.return_value = page.text
        assert (
            nolicense.edit_page(
                page,
                text="NewText",
                summary="Summary",
                throttle=throttle,
                mode=mock.sentinel.mode,
                new_ok=True,
            )
            is True
        )
        save_page.assert_called_once_with(
            page=page,
            text="NewText",
            summary="Summary",
            bot=False,
            minor=False,
            mode=mock.sentinel.mode,
            force=False,
            new_ok=True,
        )
    throttle_throttle.assert_called_once()


def test_edit_page_nothrottle():
    with mock.patch("utils.save_page") as save_page:
        page = mock.Mock(spec=pywikibot.Page, text="foo")
        page.get.return_value = page.text
        nolicense.edit_page(
            page,
            text="NewText",
            summary="Summary",
            throttle=None,
            mode=mock.sentinel.mode,
            new_ok=False,
        )
        save_page.assert_called_once_with(
            page=page,
            text="NewText",
            summary="Summary",
            bot=False,
            minor=False,
            mode=mock.sentinel.mode,
            force=False,
            new_ok=False,
        )


def test_edit_page_simulate():
    nolicense.simulate = True
    with mock.patch("utils.save_page") as save_page:
        page = mock.Mock(spec=pywikibot.Page, text="foo")
        page.get.return_value = page.text
        nolicense.edit_page(
            page, text="NewText", summary="Summary", throttle=None,
        )
        save_page.assert_not_called()
    nolicense.simulate = None


def test_edit_page_exception():
    throttle = mock.Mock()
    with mock.patch("utils.save_page", side_effect=utils.RunpageError) as save_page:
        page = mock.Mock(spec=pywikibot.Page, text="foo")
        page.get.return_value = page.text
        assert (
            nolicense.edit_page(
                page, text="NewText", summary="Summary", throttle=throttle,
            )
            is False
        )
        save_page.assert_called()


@pytest.mark.parametrize(
    "grouped,queue_titles",
    [(False, ["page1"]), (True, ["page1"]), (True, ["page1", "page2"])],
)
def test_warn_user(grouped, queue_titles):
    test_config = {
        "warn_text": "warn_text($title, $also)",
        "warn_also": "warn_also()",
        "warn_also_line": "warn_also_line($link)",
        "warn_summary": "warn_summary($version)",
        "group_warnings": grouped,
    }
    queue = collections.deque(
        mock.Mock(spec=pywikibot.Page, title=mock.Mock(return_value=queue_title))
        for queue_title in queue_titles
    )
    user_talk = mock.Mock(title=mock.Mock(return_value="user_talk"), text="old_text()")
    user_talk.get.return_value = user_talk.text
    with mock.patch.dict("nolicense.config", test_config):
        with mock.patch("nolicense.edit_page") as edit_page:
            assert (
                nolicense.warn_user(
                    user_talk=user_talk, queue=queue, throttle=mock.sentinel.throttle,
                )
                == collections.deque()
            )
            text = edit_page.call_args[0][1]
            edit_page.assert_called_once_with(
                user_talk,
                mock.ANY,
                f"warn_summary({nolicense.__version__})",
                throttle=mock.sentinel.throttle,
                mode="append",
                force=True,
                new_ok=True,
            )
            assert f"warn_text({queue_titles[0]}," in text
            if grouped and len(queue_titles) > 1:
                assert "warn_also()" in text
                for page in queue_titles[1:]:
                    assert f"warn_also_line({page}" in text
            else:
                assert "warn_also()" not in text


def test_warn_user_ungrouped():
    queue_titles = ["page1", "page2"]
    test_config = {
        "warn_text": "warn_text($title, $also)",
        "warn_also": "warn_also()",
        "warn_also_line": "warn_also_line($link)",
        "warn_summary": "warn_summary($version)",
        "group_warnings": False,
    }
    queue = collections.deque(
        mock.Mock(spec=pywikibot.Page, title=mock.Mock(return_value=queue_title))
        for queue_title in queue_titles
    )
    user_talk = mock.Mock(title=mock.Mock(return_value="user_talk"), text="old_text()")
    user_talk.get.return_value = user_talk.text
    with mock.patch.dict("nolicense.config", test_config):
        with mock.patch("nolicense.edit_page") as edit_page:
            with pytest.raises(IndexError):
                nolicense.warn_user(
                    user_talk=user_talk, queue=queue, throttle=mock.sentinel.throttle,
                )
            edit_page.assert_not_called()


def test_warn_user_empty():
    test_config = {
        "warn_text": "warn_text($title, $also)",
        "warn_also": "warn_also()",
        "warn_also_line": "warn_also_line($link)",
        "warn_summary": "warn_summary($version)",
        "group_warnings": True,
    }
    queue = collections.deque()
    user_talk = mock.Mock(title=mock.Mock(return_value="user_talk"), text="old_text()")
    user_talk.get.return_value = user_talk.text
    with mock.patch.dict("nolicense.config", test_config):
        with mock.patch("nolicense.edit_page") as edit_page:
            nolicense.warn_user(
                user_talk=user_talk, queue=queue, throttle=mock.sentinel.throttle,
            )
            edit_page.assert_not_called()


def test_warn_user_conflict():
    test_config = {
        "warn_text": "warn_text($title, $also)",
        "warn_also": "warn_also()",
        "warn_also_line": "warn_also_line($link)",
        "warn_summary": "warn_summary($version)",
        "group_warnings": True,
    }
    queue = collections.deque(
        [mock.Mock(spec=pywikibot.Page, title=mock.Mock(return_value="page_1"))]
    )
    user_talk = mock.Mock(title=mock.Mock(return_value="user_talk"), text="old_text()")
    user_talk.get.side_effect = [user_talk.text, "new_old_text()"]
    user_talk.save.side_effect = [pywikibot.exceptions.EditConflict(user_talk), None]
    with mock.patch.dict("nolicense.config", test_config):
        nolicense.warn_user(
            user_talk=user_talk, queue=queue, throttle=None,
        )


def test_tag_page():
    test_config = {"tag_text": "tag_text()", "tag_summary": "tag_summary($version)"}
    page = mock.Mock(text="old_text()", spec=pywikibot.Page)
    page.get.return_value = page.text
    with mock.patch.dict("nolicense.config", test_config):
        with mock.patch("nolicense.edit_page") as edit_page:
            nolicense.tag_page(page, mock.sentinel.throttle)
            edit_page.assert_called_once_with(
                page,
                "tag_text()",
                f"tag_summary({nolicense.__version__})",
                throttle=mock.sentinel.throttle,
                mode="prepend",
            )


@mock.patch("utils.get_replag", return_value=datetime.timedelta(seconds=0))
@mock.patch("nolicense.check_templates", return_value=True)
@mock.patch("nolicense.tag_page", return_value=True)
@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5])
def test_main(tag_page, check_templates, get_replag, limit):
    pages = [
        mock.Mock(spec=pywikibot.Page, title=lambda: "page1"),
        mock.Mock(spec=pywikibot.Page, title=lambda: "page2"),
        mock.Mock(spec=pywikibot.Page, title=lambda: "page3"),
        mock.Mock(spec=pywikibot.Page, title=lambda: "page4"),
        mock.Mock(spec=pywikibot.Page, title=lambda: "page5"),
    ]
    users = [
        mock.sentinel.user1,
        mock.sentinel.user2,
        mock.sentinel.user2,
        mock.sentinel.user3,
        mock.sentinel.user4,
    ]
    iterpages = mock.MagicMock(return_value=zip(pages, users))
    with mock.patch("nolicense.iter_files_and_users", iterpages):
        with mock.patch(
            "nolicense.warn_user",
            side_effect=[
                collections.deque(),
                collections.deque(),
                collections.deque(),
                collections.deque(),
                collections.deque(),
                collections.deque(),
            ],
        ) as warn_user:
            nolicense.main(limit=limit, days=mock.sentinel.days)
            assert warn_user.call_count == sum([1, 1, 0, 1, 1][:limit])
            warn_user.assert_has_calls(
                [
                    mock.call(mock.sentinel.user1, collections.deque([pages[0]]),),
                    mock.call(
                        mock.sentinel.user2,
                        collections.deque(pages[1:3] if limit > 2 else [pages[1]]),
                    ),
                    mock.call(mock.sentinel.user3, collections.deque([pages[3]])),
                ][: sum([1, 1, 0, 1, 1][:limit])]
            )
            assert check_templates.call_count == limit
            check_templates.assert_has_calls(
                [mock.call(call) for call in pages[:limit]]
            )
            assert tag_page.call_count == limit
            tag_page.assert_has_calls(
                [mock.call(call, throttle=mock.ANY) for call in pages[:limit]]
            )

@mock.patch("utils.get_replag", return_value=datetime.timedelta(seconds=0))
@mock.patch("nolicense.check_templates", return_value=True)
@mock.patch("nolicense.tag_page", return_value=True)
def test_bep(tag_page, check_templates, get_replag):
    page =  pywikibot.Page(site, "User:AntiCompositeBot/test bep")
    user = mock.sentinel.user1
    iterpages = mock.MagicMock(return_value=[(page, user)])
    with mock.patch("nolicense.iter_files_and_users", iterpages):
        nolicense.main(limit=1, days=mock.sentinel.days)
        check_templates.assert_not_called()


@mock.patch("utils.get_replag", return_value=datetime.timedelta(seconds=0))
@mock.patch("nolicense.check_templates", return_value=True)
@mock.patch("nolicense.tag_page", return_value=True)
def test_skip_files(tag_page, check_templates, get_replag):
    page =  pywikibot.Page(site, "User:AntiCompositeBot/test bep")
    user = mock.sentinel.user1
    iterpages = mock.MagicMock(return_value=[(page, user)])
    test_config = {"skip_files": "File: PNG Test.png"}
    with mock.patch.dict("nolicense.config", test_config):
        with mock.patch("nolicense.iter_files_and_users", iterpages):
            nolicense.main(limit=1, days=mock.sentinel.days)
            check_templates.assert_not_called()

