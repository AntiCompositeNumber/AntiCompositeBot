#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: Apache-2.0


# Copyright 2022 AntiCompositeNumber

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
import datetime
import pytest
import string
from unittest import mock

sys.path.append(os.path.realpath(os.path.dirname(__file__) + "/.."))
os.environ["LOG_FILE"] = "stderr"
import catcron  # noqa: E402

DAYS = [
    datetime.date(2022, 1, 1),
    datetime.date(2022, 1, 2),
    datetime.date(2022, 2, 1),
    datetime.date(2022, 2, 2),
]
BLANK = string.Template("")


@mock.patch("acnutils.check_runpage")
class TestShouldRun:
    @pytest.mark.parametrize(["today", "expected"], zip(DAYS, [True, True, True, True]))
    def test_daily(self, runpage: mock.Mock, today: datetime.datetime, expected: bool):
        target = catcron.Target("daily", BLANK, BLANK)
        assert target.should_run(today) is expected
        with mock.patch("acnutils.save_page") as save_page:
            with mock.patch("pywikibot.Page.exists", return_value=False):
                target.create(today)
                if expected:
                    save_page.assert_called_once()
                else:
                    save_page.assert_not_called()

    @pytest.mark.parametrize(
        ["today", "expected"], zip(DAYS, [True, False, True, False])
    )
    def test_monthly(
        self, runpage: mock.Mock, today: datetime.datetime, expected: bool
    ):
        target = catcron.Target("monthly", BLANK, BLANK)
        assert target.should_run(today) is expected
        with mock.patch("acnutils.save_page") as save_page:
            with mock.patch("pywikibot.Page.exists", return_value=False):
                target.create(today)
                if expected:
                    save_page.assert_called_once()
                else:
                    save_page.assert_not_called()

    @pytest.mark.parametrize(
        ["today", "expected"], zip(DAYS, [True, False, False, False])
    )
    def test_yearly(self, runpage: mock.Mock, today: datetime.datetime, expected: bool):
        target = catcron.Target("yearly", BLANK, BLANK)
        assert target.should_run(today) is expected
        with mock.patch("acnutils.save_page") as save_page:
            with mock.patch("pywikibot.Page.exists", return_value=False):
                target.create(today)
                if expected:
                    save_page.assert_called_once()
                else:
                    save_page.assert_not_called()


@pytest.mark.parametrize(
    ["target", "title", "text"],
    [
        (
            catcron.Target(
                "daily",
                string.Template("Permission pending as of $day $monthname $year"),
                string.Template(
                    "{{Permission pending header|day=$day|month=$monthname|year=$year}}"
                ),
            ),
            "Category:Permission pending as of 1 February 2022",
            "{{Permission pending header|day=1|month=February|year=2022}}",
        ),
        (
            catcron.Target(
                "monthly",
                string.Template(
                    "Category:Commons users indefinitely blocked in $monthname $year"
                ),
                string.Template(
                    "[[Category:Commons users indefinitely blocked|$year-$month]]"
                ),
            ),
            "Category:Commons users indefinitely blocked in February 2022",
            "[[Category:Commons users indefinitely blocked|2022-02]]",
        ),
    ],
)
@mock.patch("acnutils.check_runpage")
def test_create(runpage: mock.Mock, target: catcron.Target, title: str, text: str):
    date = datetime.date(2022, 2, 1)
    with mock.patch("acnutils.save_page") as save_page:
        with mock.patch("pywikibot.Page.exists", return_value=False):
            target.create(date)
            save_page.assert_called_once()
            assert save_page.call_args.kwargs["page"].title() == title
            assert save_page.call_args.kwargs["text"] == text

    runpage.assert_called()


@pytest.mark.parametrize(
    "target",
    [
        catcron.Target(
            "monthly",
            string.Template(
                "Category:Commons users indefinitely blocked in $monthname $year"
            ),
            string.Template(
                "[[Category:Commons users indefinitely blocked|$year-$month]]"
            ),
        ),
    ],
)
def test_create_exists(target: catcron.Target):
    date = datetime.date(2022, 1, 1)
    with mock.patch("acnutils.save_page") as save_page:
        target.create(date)
        save_page.assert_not_called()
