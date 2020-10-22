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
import utils
import logging
import logging.config
import requests
import re
import csv
import math
import ipaddress
import json
from typing import NamedTuple
from pprint import pprint

__version__ = "0.1"

logging.config.dictConfig(
    utils.logger_config("ASNBlock", level="INFO", filename="asnblock.log")
)
logger = logging.getLogger("ASNBlock")

site = pywikibot.Site("en", "wikipedia")
cluster = "web"
simulate = None
session = requests.session()
session.headers.update({"User-Agent": toolforge.set_user_agent("anticompositebot")})


class DataRow(NamedTuple):
    registry: str
    cc: str
    type: str
    start: str
    value: str
    date: str
    status: str
    opaque_id: str


def get_config():
    page = pywikibot.Page(site, "User:AntiCompositeBot/ASNBlock/config.json")
    data = json.loads(page.text)
    return data


class RIRData:
    def __init__(self):
        self.load_rir_data()

    def get_rir_data(self):
        data_urls = dict(
            APNIC="https://ftp.apnic.net/stats/apnic/delegated-apnic-extended-latest",
            AFRNIC="https://ftp.afrinic.net/pub/stats/afrinic/delegated-afrinic-extended-latest",  # noqa: E501
            ARIN="https://ftp.arin.net/pub/stats/arin/delegated-arin-extended-latest",
            LACNIC="https://ftp.lacnic.net/pub/stats/lacnic/delegated-lacnic-extended-latest",  # noqa: E501
            RIPE="https://ftp.ripe.net/ripe/stats/delegated-ripencc-extended-20201021",
        )
        filter_regex = re.compile(r"^(?:#|\d|.*\*|.*available)")
        for url in data_urls.values():
            print(url)
            req = session.get(url)
            req.raise_for_status()
            for line in req.text.split("\n"):
                if re.match(filter_regex, line) or not line:
                    continue
                else:
                    yield line

    def load_rir_data(self):
        ipv4 = []
        ipv6 = []
        asn = []
        reader = csv.reader(self.get_rir_data(), delimiter="|")
        for line in reader:
            row = DataRow._make(line)
            if row.type == "ipv4":
                ipv4.append(row)
            elif row.type == "ipv6":
                ipv6.append(row)
            elif row.type == "asn":
                asn.append(row)
        self.ipv4 = ipv4
        self.ipv6 = ipv6
        self.asn = asn

    def get_asn_ranges(self, asn_list):
        idents = [row.opaque_id for row in self.asn if row.start in asn_list]
        ranges = []
        # IPv4 records are starting ip & total IPs
        # Need to do some math to get CIDR ranges
        ranges.extend(
            ipaddress.IPv4Network(row.start, 32 - int(math.log2(row.value)))
            for row in self.ipv4
            if row.opaque_id in idents
        )
        # IPv6 records just have the CIDR range.
        ranges.extend(
            ipaddress.IPv6Network(row.start, row.value)
            for row in self.ipv6
            if row.opaque_id in idents
        )
        return ranges


def search_whois(net, search_list):
    url = "https://whois.toolforge.org/gateway.py"
    params = {
        "ip": net[0],
        "lookup": "true",
        "format": "json",
    }
    req = session.get(url, params=params)
    req.raise_for_status()
    for whois_net in req.json()["nets"]:
        for search in search_list:
            if (
                search in whois_net.get("description", "").lower()
                or search in whois_net.get("name", "").lower()
            ):
                return True
    return False


def not_blocked(addr):
    query = """
SELECT ipb_id
FROM ipblocks
WHERE ipb_address = %s
AND ipb_user = 0"""
    conn = toolforge.connect("enwiki")
    with conn.cursor() as cur:
        cur.execute(query, args=(addr.exploded.replace("0000", "0")))
        return not len(cur.fetchall()) > 0


def main():
    providers = get_config()
    rir_data = RIRData()

    for name, provider in providers.items():
        print(name)
        if "asn" in provider.keys():
            ranges = rir_data.get_asn_ranges(provider["asn"])
        elif "url" in provider.keys():
            pass
        ranges = filter(ranges, not_blocked)
        if "search" in provider.keys():
            ranges = [net for net in ranges if search_whois(net, provider["search"])]
        pprint(ranges)
