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
import pywikibot
import unittest.mock as mock
import pytest

sys.path.append(os.path.realpath(os.path.dirname(__file__) + "/.."))
import utils  # noqa:E402


@pytest.mark.parametrize(
    "mode,text,new_text",
    [
        ("replace", "[new_text]", "[new_text]"),
        ("append", "[new_text]", "[old_text][new_text]"),
        ("prepend", "[new_text]", "[new_text][old_text]"),
        ("append", "[old_text]", "[old_text][old_text]"),
        ("prepend", "[old_text]", "[old_text][old_text]"),
    ],
)
def test_save_page(mode, text, new_text):
    mock_page = mock.Mock(spec=pywikibot.page.Page, text="[old_text]")
    mock_page.get.return_value = mock_page.text
    mock_save = mock.Mock()
    mock_page.save = mock_save
    utils.save_page(
        text=text,
        page=mock_page,
        summary=mock.sentinel.summary,
        minor=mock.sentinel.minor,
        bot=mock.sentinel.bot,
        mode=mode,
    )
    mock_save.assert_called_once_with(
        summary=mock.sentinel.summary,
        minor=mock.sentinel.minor,
        botflag=mock.sentinel.bot,
        quiet=True,
    )
    assert mock_page.text == new_text


@pytest.mark.parametrize(
    "mode,text,exception",
    [
        ("replace", "", pywikibot.exceptions.PageNotSaved),
        ("append", "", pywikibot.exceptions.PageNotSaved),
        ("prepend", "", pywikibot.exceptions.PageNotSaved),
        ("delete", "foo", ValueError),
        ("replace", "[old_text]", pywikibot.exceptions.PageNotSaved),
    ],
)
def test_save_page_except(mode, text, exception):
    mock_page = mock.Mock(spec=pywikibot.page.Page, text="[old_text]")
    mock_page.get.return_value = mock_page.text
    mock_save = mock.Mock()
    mock_page.save = mock_save
    with pytest.raises(exception):
        utils.save_page(
            text=text,
            page=mock_page,
            summary=mock.sentinel.summary,
            minor=mock.sentinel.minor,
            bot=mock.sentinel.bot,
            mode=mode,
        )
