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
import time
import datetime
import itertools
import sys

session = requests.Session()
session.headers.update(
    {"User-Agent": "sigprobs " + toolforge.set_user_agent("anticompositebot")}
)


def iter_active_user_sigs(dbname, startblock=0):
    conn = toolforge.connect(f"{dbname}_p")
    with conn.cursor(cursor=pymysql.cursors.SSCursor) as cur:
        for i in range(startblock, 100):
            cur.execute(
                """
                SELECT user_name, up_value
                FROM
                    user_properties
                    JOIN `user` ON user_id = up_user
                WHERE
                    RIGHT(up_user, 2) = %s AND
                    up_property = "nickname" AND
                    user_name IN (SELECT actor_name
                                  FROM revision_userindex
                                  JOIN actor_revision ON rev_actor = actor_id
                                  WHERE rev_timestamp > 20190304000000) AND
                    up_user IN (SELECT up_user
                                FROM user_properties
                                WHERE up_property = "fancysig" AND up_value = 1) AND
                    up_value != user_name
                ORDER BY up_user ASC""",
                args=(str(i)),
            )
            print(f"Block {i}")
            for username, signature in cur.fetchall_unbuffered():
                yield username.decode(encoding="utf-8"), signature.decode(
                    encoding="utf-8"
                )


def get_site_data(hostname):
    url = f"https://{hostname}/w/api.php"
    data = dict(
        action="query",
        meta="siteinfo",
        siprop="namespaces|specialpagealiases|magicwords|general",
        formatversion="2",
        format="json",
    )
    res = session.get(url, params=data)
    res.raise_for_status()

    namespaces = res.json()["query"]["namespaces"]
    specialpages = {
        item["realname"]: item["aliases"]
        for item in res.json()["query"]["specialpagealiases"]
    }
    magicwords = {
        item["name"]: item["aliases"] for item in res.json()["query"]["magicwords"]
    }
    general = res.json()["query"]["general"]

    contribs = set()
    for name in specialpages["Contributions"]:
        contribs.update(
            (special + ":" + name)
            for special in [namespaces["-1"]["name"], namespaces["-1"]["canonical"]]
        )

    subst = list(
        itertools.chain(
            magicwords.get("subst", ["SUBST"]),
            [item.lower() for item in magicwords.get("subst", ["SUBST"])],
            [item[0] + item[1:].lower() for item in magicwords.get("subst", ["SUBST"])],
        )
    )

    sitedata = {
        "user": {namespaces["2"]["name"], namespaces["2"]["canonical"]},
        "user talk": {namespaces["3"]["name"], namespaces["3"]["canonical"]},
        "contribs": contribs,
        "subst": subst,
        "dbname": general["wikiid"],
    }
    return sitedata


def check_sig(user, sig, sitedata, hostname):
    errors = set()
    if not sig:
        return {"blank-sig"}
    try:
        errors.update(get_lint_errors(sig, hostname))
    except Exception:
        for i in range(0, 5):
            print(f"Request failed, sleeping for {3**i}")
            time.sleep(3 ** i)
            errors.update(get_lint_errors(sig, hostname))
            break
        else:
            raise

    errors.add(check_tildes(sig))
    errors.add(check_links(user, sig, sitedata, hostname))
    errors.add(check_fanciness(sig))
    errors.add(check_length(sig))
    return errors - {""}


def get_lint_errors(sig, hostname):
    url = f"https://{hostname}/api/rest_v1/transform/wikitext/to/lint"
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


def check_links(user, sig, sitedata, hostname):
    goodlinks = set(
        itertools.chain(
            *(
                [f"{ns}:{user}".lower().replace(" ", "_") for ns in sitedata[key]]
                for key in ["user", "user talk"]
            ),
            (
                f"{cont}/{user}".lower().replace(" ", "_")
                for cont in sitedata["contribs"]
            ),
        )
    )

    if compare_links(goodlinks, sig) or compare_links(
        goodlinks, evaluate_subst(sig, sitedata, hostname)
    ):
        return ""
    else:
        return "no-user-links"


def evaluate_subst(text, sitedata, hostname):
    for subst in sitedata["subst"]:
        text = text.replace(subst, "")
    data = {
        "action": "expandtemplates",
        "format": "json",
        "text": text,
        "prop": "wikitext",
    }
    url = f"https://{hostname}/w/api.php"
    res = session.get(url, params=data)
    res.raise_for_status()
    return res.json()["expandtemplates"]["wikitext"]


def check_fanciness(sig):
    fancychars = {"'", "<", "[", "{"}
    for letter in sig:
        if letter in fancychars:
            return ""
    else:
        return "plain-fancy-sig"


def compare_links(goodlinks, sig):
    wikitext = mwph.parse(sig)
    for link in wikitext.ifilter_wikilinks():
        if str(link.title).lower().replace(" ", "_") in goodlinks:
            return True
    else:
        return False


def check_tildes(sig):
    if sig.count("~") >= 3:
        return "nested-subst"
    else:
        return ""


def check_length(sig):
    if len(sig) > 255:
        return "sig-too-long"
    else:
        return ""


def main(hostname, startblock=0):
    bad = 0
    total = 0

    sitedata = get_site_data(hostname)

    dbname = sitedata["dbname"]

    filename = f"/data/project/anticompositebot/www/static/{dbname}_sigprobs.json"
    # Clear file to begin
    if not startblock:
        with open(filename + "l", "w") as f:
            f.write("")

    # Collect data into json lines file
    # Data is written directly as json lines to prevent data loss on database error
    for user, sig in iter_active_user_sigs(dbname, startblock):
        total += 1
        try:
            errors = check_sig(user, sig, sitedata, hostname)
        except Exception:
            print(user, sig)
            raise
        if not errors:
            continue
        sigerror = {"username": user, "signature": sig, "errors": list(errors)}
        with open(filename + "l", "a") as f:
            f.write(json.dumps(sigerror) + "\n")
        bad += 1
        if bad % 10 == 0:
            print(f"{bad} bad sigs found in {total} so far")

    # Read back data, collect stats, and generate json file
    fulldata = {}
    stats = {}
    stats["total"] = bad
    with open(filename + "l") as f:
        for rawline in f:
            line = json.loads(rawline)
            for error in line.get("errors"):
                stats[error] = stats.setdefault(error, 0) + 1
            fulldata[line.pop("username")] = line

    meta = {"last_update": datetime.datetime.utcnow().isoformat(), "site": hostname}
    with open(filename, "w") as f:
        json.dump(
            {"errors": stats, "meta": meta, "sigs": fulldata},
            f,
            sort_keys=True,
            indent=4,
        )


if __name__ == "__main__":
    error_sigs = main(sys.argv[1])
