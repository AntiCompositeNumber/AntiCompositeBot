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


import requests
import mwparserfromhell as mwph
import toolforge
import json
import pymysql

session = requests.Session()
session.headers.update(
    {"User-Agent": "sigprobs " + toolforge.set_user_agent("anticompositebot")}
)


def iter_active_user_sigs():
    conn = toolforge.connect("enwiki_p")
    with conn.cursor(cursor=pymysql.cursors.SSCursor) as cur:
        for i in range(0, 10):
            cur.execute(
                """
                SELECT user_name, up_value
                FROM
                    user_properties
                    JOIN `user` ON user_id = up_user
                WHERE
                    RIGHT(up_user, 1) = 0 AND
                    up_property = "nickname" AND
                    user_name IN (SELECT actor_name
                                  FROM revision_userindex
                                  JOIN actor_revision ON rev_actor = actor_id
                                  WHERE rev_timestamp > 20190304000000) AND
                    up_user IN (SELECT up_user
                                FROM user_properties
                                WHERE up_property = "fancysig" AND up_value = 1) AND
                    up_value != user_name
            """,
                args=(i),
            )
            for username, signature in cur.fetchall_unbuffered():
                yield username.decode(encoding="utf-8"), signature.decode(
                    encoding="utf-8"
                )


def check_sig(user, sig):
    errors = set()
    errors.update(get_lint_errors(sig))
    errors.add(check_tildes(sig))
    errors.add(check_links(user, sig))
    errors.add(check_length(sig))
    return errors - {""}


def get_lint_errors(sig):
    url = "https://en.wikipedia.org/api/rest_v1/transform/wikitext/to/lint"
    data = {"wikitext": sig}
    res = session.post(url, json=data)
    res.raise_for_status()
    errors = set()
    for error in res.json():
        if (
            error.get("type", "") == "obsolete-tag"
            and error.get("params", {}).get("name", "") == "font"
        ):
            errors.add("obsolete-font-tag")
        else:
            errors.add(error.get("type"))
    return errors


def check_links(user, sig):
    wikitext = mwph.parse(sig)
    goodlinks = {
        f"User:{user}",
        f"User talk:{user}",
        f"Special:Contribs/{user}",
        f"Special:Contributions/{user}",
    }
    for link in wikitext.ifilter_wikilinks():
        if str(link.title) in goodlinks:
            break
    else:
        return "no-user-links"
    return ""


def check_tildes(sig):
    if "~~" in sig:
        return "nested-subst"
    else:
        return ""


def check_length(sig):
    if len(sig) > 255:
        return "sig-too-long"
    else:
        return ""


def main():
    error_sigs = {}
    i = 0
    for user, sig in iter_active_user_sigs():
        errors = check_sig(user, sig)
        if not errors:
            continue
        error_sigs[user] = {"signature": sig, "errors": errors}
        i += 1
        if i % 25 == 0:
            print(i)

    return error_sigs


if __name__ == "__main__":
    error_sigs = main()
    with open("/data/project/anticompositebot/www/static/sigprobs.json", "w") as f:
        json.dump(error_sigs, f, sort_keys=True, indent=4)
