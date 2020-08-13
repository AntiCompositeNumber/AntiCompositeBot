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
import toolforge
import datetime
import itertools
from typing import NamedTuple
import utils

site = pywikibot.Site("en", "wikipedia")
__version__ = "1.1"


class Row(NamedTuple):
    username: str
    edit_count: int
    registration_date: datetime.datetime
    ext_conf: bool
    redwarn_edits: int
    redwarn_pct: float
    blocked: bool

    def tablerow(self):
        return "|" + "||".join(str(val) for val in self)

    @staticmethod
    def header():
        return "!" + "!!".join(
            [
                "Username",
                "Edit count",
                "Registration date",
                "30/500",
                "RedWarn edits",
                "RedWarn %",
                "Blocked",
            ]
        )


def run_query():
    query = """
SELECT
    actor_name as `username`,
    user_editcount as `edit_count`,
    user_registration as `registration_date`,
    NOT(ug_group IS NULL)  as `ext_conf`,
    COUNT(*) as `redwarn_edits`,
    COUNT(*)/user_editcount*100 as `redwarn_pct`,
    ipb_sitewide as `blocked`
FROM revision_userindex
JOIN change_tag ON ct_rev_id = rev_id
JOIN actor_revision ON rev_actor = actor_id
JOIN `user` ON actor_user = user_id
LEFT JOIN user_groups ON ug_user = user_id AND ug_group = "extendedconfirmed"
LEFT JOIN ipblocks ON user_id = ipb_user
WHERE ct_tag_id = 577 -- RedWarn
GROUP BY actor_name
ORDER BY user_registration DESC
"""
    conn = toolforge.connect("enwiki_p")
    with conn.cursor() as cur:
        cur.execute(query)
        data = cur.fetchall()
    for line in data:
        yield Row(
            username=f"[[User:{str(line[0], encoding='utf-8')}]]",
            edit_count=line[1],
            registration_date=datetime.datetime.strptime(
                str(line[2], encoding="utf-8"), "%Y%m%d%H%M%S"
            ),
            ext_conf=bool(line[3]),
            redwarn_edits=line[4],
            redwarn_pct=line[5],
            blocked=bool(line[6]),
        )


def make_table(data):
    info = f"Last updated by AntiCompositeBot at {datetime.datetime.now()}\n\n"
    return info + "\n|-\n".join(
        itertools.chain(
            ['{| class="wikitable sortable"', Row.header()],
            [row.tablerow() for row in data],
            ["|}"],
        )
    )


def main():
    data = run_query()
    table = make_table(data)
    page = pywikibot.Page(site, "User:AntiCompositeBot/RedWarn users")
    utils.save_page(
        text=table,
        page=page,
        summary=f"Updating statistics (RWU {__version__}) (Bot)",
        mode="replace",
        bot=False,
        minor=True,
    )


if __name__ == "__main__":
    main()
