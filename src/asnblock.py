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


import pywikibot  # type: ignore
import toolforge  # type: ignore
import utils
import logging
import logging.config
import requests
import re
import csv
import math
import ipaddress
import json
import urllib.parse
import sys
from bs4 import BeautifulSoup  # type: ignore
import pymysql
from typing import NamedTuple, Union, Dict, List, Iterator, Sequence, cast

__version__ = "0.2"

logging.config.dictConfig(
    utils.logger_config("ASNBlock", level="VERBOSE", filename="asnblock.log")
)
logger = logging.getLogger("ASNBlock")

site = pywikibot.Site("en", "wikipedia")
simulate = False
session = requests.session()
session.headers.update({"User-Agent": toolforge.set_user_agent("anticompositebot")})

IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


class DataRow(NamedTuple):
    registry: str
    cc: str
    type: str
    start: str
    value: str
    date: str
    status: str
    opaque_id: str


def get_config() -> Dict[str, List[Dict[str, Union[str, List[str]]]]]:
    page = pywikibot.Page(site, "User:AntiCompositeBot/ASNBlock/config.json")
    data = json.loads(page.text)
    return data


class RIRData:
    def __init__(self) -> None:
        self.load_rir_data()

    def get_rir_data(self) -> Iterator[str]:
        data_urls = dict(
            APNIC="https://ftp.apnic.net/stats/apnic/delegated-apnic-extended-latest",
            AFRNIC="https://ftp.afrinic.net/pub/stats/afrinic/delegated-afrinic-extended-latest",  # noqa: E501
            ARIN="https://ftp.arin.net/pub/stats/arin/delegated-arin-extended-latest",
            LACNIC="https://ftp.lacnic.net/pub/stats/lacnic/delegated-lacnic-extended-latest",  # noqa: E501
            RIPE="https://ftp.ripe.net/ripe/stats/delegated-ripencc-extended-latest",
        )
        filter_regex = re.compile(r"^(?:#|\d|.*\*)")
        regex2 = re.compile(r"(?:allocated|assigned)")
        for rir, url in data_urls.items():
            logger.info(f"Loading range data from {rir}")
            req = session.get(url)
            req.raise_for_status()
            for line in req.text.split("\n"):
                if (
                    re.match(filter_regex, line)
                    or not line
                    or not re.search(regex2, line)
                ):
                    continue
                else:
                    yield line

    def load_rir_data(self) -> None:
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
        logger.info("Range data loaded")

    def get_asn_ranges(self, asn_list: List[str]):
        # The RIR data files don't prefix AS numbers with AS, so remove it
        for i, asn in enumerate(asn_list.copy()):
            if asn.startswith("AS"):
                asn_list[i] = asn[2:]

        idents = [row.opaque_id for row in self.asn if row.start in asn_list]
        ranges: List[IPNetwork] = []
        # IPv4 records are starting ip & total IPs
        # Need to do some math to get CIDR ranges
        ranges.extend(
            ipaddress.IPv4Network((row.start, 32 - int(math.log2(int(row.value)))))
            for row in self.ipv4
            if row.opaque_id in idents
        )
        # IPv6 records just have the CIDR range.
        ranges.extend(
            ipaddress.IPv6Network((row.start, int(row.value)))
            for row in self.ipv6
            if row.opaque_id in idents
        )
        return ranges


def microsoft_data() -> Iterator[IPNetwork]:
    url = "https://www.microsoft.com/en-us/download/confirmation.aspx?id=56519"
    gate = session.get(url)
    gate.raise_for_status()
    soup = BeautifulSoup(gate.text, "html.parser")
    link = soup.find("a", class_="failoverLink").get("href")
    req = session.get(link)
    req.raise_for_status()
    data = req.json()
    for group in data["values"]:
        for prefix in group["properties"]["addressPrefixes"]:
            yield ipaddress.ip_network(prefix)


def amazon_data(provider: Dict[str, Union[str, List[str]]]) -> Iterator[IPNetwork]:
    url = cast(str, provider["url"])
    req = session.get(url)
    req.raise_for_status()
    data = req.json()
    for prefix in data["prefixes"]:
        yield ipaddress.IPv4Network(prefix["ip_prefix"])
    for prefix in data["ipv6_prefixes"]:
        yield ipaddress.IPv6Network(prefix["ipv6_prefix"])


def google_data() -> Iterator[IPNetwork]:
    url = "https://www.gstatic.com/ipranges/cloud.json"
    req = session.get(url)
    req.raise_for_status()
    data = req.json()
    for prefix in data["prefixes"]:
        if "ipv4Prefix" in prefix.keys():
            yield ipaddress.ip_network(prefix["ipv4Prefix"])
        if "ipv6Prefix" in prefix.keys():
            yield ipaddress.ip_network(prefix["ipv6Prefix"])


def search_whois(net: IPNetwork, search_list: Sequence[str]):
    logger.debug(f"Searching WHOIS for {search_list} in {net}")
    url = "https://whois.toolforge.org/gateway.py"
    params = {
        "ip": net[0],
        "lookup": "true",
        "format": "json",
    }
    try:
        req = session.get(url, params=params)
        req.raise_for_status()
        for whois_net in req.json()["nets"]:
            for search in search_list:
                if (
                    search in str(whois_net.get("description", "")).lower()
                    or search in str(whois_net.get("name", "")).lower()
                ):
                    return True
    except Exception as e:
        logger.exception(e)
    return False


def not_blocked(net: IPNetwork, conn: pymysql.connections.Connection) -> bool:
    logger.debug(f"Checking for blocks on {net}")
    # MediaWiki does some crazy stuff here. Re-implementation of parts of
    # MediaWiki\ApiQueryBlocks, Wikimedia\IPUtils, Wikimedia\base_convert
    if net.version == 4:
        start = "%08X" % int(net.network_address)
        end = "%08X" % (int(net.network_address) + 2 ** (32 - net.prefixlen) - 1)
        prefix = start[:4] + "%"
    elif net.version == 6:
        rawnet = "".join(
            format(part, "0>4") for part in str(net.network_address.exploded).split(":")
        )
        net6 = int(
            format(format(int(rawnet, base=16), "0>128b")[: net.prefixlen], "0<128"),
            base=2,
        )
        start = "v6-%032X" % net6
        end = "v6-%032X" % int(
            format(format(net6, "0>128b")[: net.prefixlen], "1<128"), base=2
        )
        prefix = start[:7] + "%"

    if conn.db == b"centralauth_p":
        query = """
SELECT gb_id
FROM globalblocks
WHERE
    gb_range_start LIKE %(prefix)s
    AND gb_range_start <= %(start)s
    AND gb_range_end >= %(end)s
"""
    else:
        query = """
SELECT ipb_id
FROM ipblocks
WHERE
    ipb_range_start LIKE %(prefix)s
    AND ipb_range_start <= %(start)s
    AND ipb_range_end >= %(end)s
    AND ipb_sitewide = 1
    AND ipb_auto = 0
"""
    try:
        with conn.cursor() as cur:
            count = cur.execute(query, args=dict(start=start, end=end, prefix=prefix))
            return count == 0
    except Exception as e:
        logger.exception(e)
        return False


def combine_ranges(all_ranges: Sequence[IPNetwork]) -> Iterator[IPNetwork]:
    ipv4 = [net for net in all_ranges if net.version == 4]
    ipv6 = [net for net in all_ranges if net.version == 6]
    for ranges in [ipv4, ipv6]:
        ranges = list(ipaddress.collapse_addresses(sorted(ranges)))  # type: ignore
        for net in ranges:
            if net.version == 4 and net.prefixlen < 16:
                for subnet in net.subnets(new_prefix=16):
                    yield subnet
            elif net.version == 6 and net.prefixlen < 19:
                for subnet in net.subnets(new_prefix=19):
                    yield subnet
            else:
                yield net


def make_section(provider: Dict[str, Union[str, List[str], List[IPNetwork]]]) -> str:
    if "url" in provider.keys():
        source = "[{url} {src}]".format(**provider)
    elif "asn" in provider.keys():
        source = ", ".join(
            f"[https://bgp.he.net/{asn} {asn}]" for asn in provider["asn"]
        )

    if "search" in provider.keys():
        search = " for: " + ", ".join(cast(List[str], provider["search"]))
    else:
        search = ""

    row = (
        "# [[Special:Contribs/{net}|{net}]] | "
        "[[toolforge:whois/gateway.py?lookup=true&ip={addr}|Whois]] | "
        "[https://en.wikipedia.org/wiki/Special:Block/{net}?{qs} BLOCK]\n"
    )
    ranges = ""
    for net in provider["ranges"]:
        net = cast(IPNetwork, net)
        addr = str(net.network_address)
        if (net.version == 4 and net.prefixlen == 32) or (
            net.version == 6 and net.prefixlen == 128
        ):
            ip_range = addr  # type: ignore
        else:
            ip_range = str(net)
        qs = urllib.parse.urlencode(
            {
                "wpExpiry": provider.get("expiry", ""),
                "wpHardBlock": 1,
                "wpReason": "other",
                "wpReason-other": "{{Colocationwebhost}} <!-- %s -->"
                % provider.get("blockname", provider["name"]),
            }
        )
        ranges += row.format(net=ip_range, addr=addr, name=provider["name"], qs=qs)

    section = f"==={provider['name']}===\nSearching {source}{search}\n{ranges}"
    return section


def make_mass_section(
    provider: Dict[str, Union[str, List[str], List[IPNetwork]]]
) -> str:
    section = f"==={provider['name']}===\n" + "\n".join(
        str(net) for net in provider["ranges"]
    )
    return section


def update_page(new_text: str, title: str, mass: bool = False) -> None:
    title = "User:AntiCompositeBot/" + title
    if mass:
        title += "/mass"
    page = pywikibot.Page(site, title)
    top, sep, end = page.text.partition("== Hosts ==")
    text = top + new_text
    summary = f"Updating report (Bot) (ASNBlock {__version__})"
    if simulate:
        logger.debug(f"Simulating {page.title(as_link=True)}: {summary}")
        logger.debug(text)
    else:
        utils.check_runpage(site, "ASNBlock")
        utils.save_page(
            text=text,
            page=page,
            summary=summary,
            bot=False,
            minor=False,
            mode="replace",
            force=False,
            new_ok=False,
        )


def collect_data(
    config: dict, db: str
) -> List[Dict[str, Union[str, List[str], List[IPNetwork]]]]:
    providers: List[Dict[str, Union[str, List[str]]]] = config["providers"]
    rir_data = RIRData()

    for provider in providers:
        logger.info(f"Checking ranges from {provider['name']}")
        if "asn" in provider.keys():
            ranges = rir_data.get_asn_ranges(cast(List[str], provider["asn"]).copy())
        elif "url" in provider.keys():
            if "microsoft" in provider["url"]:
                ranges = microsoft_data()
            elif "google" in provider["url"]:
                ranges = google_data()
            elif "amazon" in provider["url"]:
                ranges = amazon_data(provider)
            else:
                logger.warning(f"{provider['name']} has no handler")
                continue
        else:
            logger.warning(f"{provider['name']} could not be processed")
            continue

        ranges = combine_ranges(ranges)

        conn = toolforge.connect(db)
        for net in ranges:
            if not_blocked(net, conn) and (
                "search" not in provider.keys() or search_whois(net, provider["search"])
            ):
                cast(List[IPNetwork], provider.setdefault("ranges", [])).append(net)
        conn.close()

    return cast(List[Dict[str, Union[str, List[str], List[IPNetwork]]]], providers)


def main(db: str = "enwiki") -> None:
    utils.check_runpage(site, "ASNBlock")
    logger.info("Loading configuration data")
    config = get_config()

    providers = collect_data(config, db)

    title = "ASNBlock"
    if db == "enwiki":
        pass
    elif db == "centralauth":
        title += "/global"
    else:
        title += "/" + db

    text = mass_text = "== Hosts ==\n"
    for provider in providers:
        section = make_section(
            cast(Dict[str, Union[str, List[str], List[IPNetwork]]], provider)
        )
        text += section
    update_page(text, title=title)

    for provider in providers:
        mass_text += make_mass_section(
            cast(Dict[str, Union[str, List[str], List[IPNetwork]]], provider)
        )
    update_page(mass_text, title=title, mass=True)

    with open(
        f"/data/project/anticompositebot/www/static/{title.replace('/', '_')}.json", "w"
    ) as f:
        json.dump(providers, f)

    logger.error("Finished")


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except Exception as e:
        logger.exception(e)
        raise
