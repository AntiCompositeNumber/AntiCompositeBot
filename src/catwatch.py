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

import toolforge
import json
import datetime


def get_cat_files(category: str) -> int:
    conn = toolforge.connect("commonswiki_p")
    query = """
SELECT cat_files
FROM category
WHERE cat_title = %s
"""
    with conn.cursor() as cur:
        cur.execute(query, args=[category])
        return cur.fetchall()[0]


def write_to_file(filename: str, value: int) -> None:
    try:
        with open(filename) as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    data[datetime.datetime.now().isoformat(timespec="seconds")] = value
    with open(filename, "w") as f:
        json.dump(data, f)


def main():
    count = get_cat_files("Files_with_no_machine-readable_license")
    write_to_file(
        "/data/project/anticompositebot/www/static/"
        "Files_with_no_machine-readable_license.json",
        count,
    )
