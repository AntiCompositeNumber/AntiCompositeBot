#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: Apache-2.0


# Copyright 2021 AntiCompositeNumber

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
import string
import random
import dataclasses
import datetime
import argparse
from bs4 import BeautifulSoup  # type: ignore
import pymysql
from typing import (
    NamedTuple,
    Union,
    Dict,
    List,
    Iterator,
    Iterable,
    Optional,
    Any,
    Tuple,
    cast,
)

__version__ = "1.3"

logging.config.dictConfig(
    utils.logger_config("ASNBlock", level="VERBOSE", filename="stderr")
)
logger = logging.getLogger("ASNBlock")

site = pywikibot.Site("en", "wikipedia")
simulate = False
session = requests.session()
session.headers.update({"User-Agent": toolforge.set_user_agent("anticompositebot")})
whois_api = "https://whois-dev.toolforge.org"

IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


class DataRow(NamedTuple):
    """Represents a row in an RIR bulk report."""

    registry: str
    cc: str
    type: str
    start: str
    value: str
    date: str
    status: str
    opaque_id: str


@dataclasses.dataclass
class Provider:
    name: str
    blockname: str = ""
    asn: List[str] = dataclasses.field(default_factory=list)
    expiry: str = ""
    ranges: List[IPNetwork] = dataclasses.field(default_factory=list)
    url: str = ""
    src: str = ""
    search: List[str] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.blockname:
            self.blockname = self.name
        if self.search:
            self.search = [entry.lower() for entry in self.search]


def get_config() -> Dict[
    str, Union[Dict[str, Dict[str, str]], List[Dict[str, Union[str, List[str]]]]]
]:
    page = pywikibot.Page(site, "User:AntiCompositeBot/ASNBlock/config.json")
    data = json.loads(page.text)
    return data


class RIRData:
    def __init__(self) -> None:
        self.load_rir_data()

    def get_rir_data(self) -> Iterator[str]:
        """Iterate bulk IP and AS data from the five Regional Internet Registries."""
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
        """Download, collate, and prepare data provided by the RIRs."""
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
            elif row.type == "asn":  # pragma: no branch
                asn.append(row)
        self.ipv4 = ipv4
        self.ipv6 = ipv6
        self.asn = asn
        logger.info("Range data loaded")

    def get_asn_ranges(self, asn_list: List[str]) -> List[IPNetwork]:
        """Return a list of IP ranges associated with a list of AS numbers."""
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
    """Get IP ranges used by Azure and other Microsoft services."""
    # The IP list is not at a stable or predictable URL (it includes the hash
    # of the file itself, which we don't have yet). Instead, we have to parse
    # the "click here to download manually" link out of the download page.
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


def amazon_data(provider: Provider) -> Iterator[IPNetwork]:
    """Get IP ranges used by AWS."""
    req = session.get(provider.url)
    req.raise_for_status()
    data = req.json()
    for prefix in data["prefixes"]:
        yield ipaddress.IPv4Network(prefix["ip_prefix"])
    for prefix in data["ipv6_prefixes"]:
        yield ipaddress.IPv6Network(prefix["ipv6_prefix"])


def google_data() -> Iterator[IPNetwork]:
    """Get IP ranges used by Google Cloud Platform."""
    url = "https://www.gstatic.com/ipranges/cloud.json"
    req = session.get(url)
    req.raise_for_status()
    data = req.json()
    for prefix in data["prefixes"]:
        if "ipv4Prefix" in prefix.keys():
            yield ipaddress.ip_network(prefix["ipv4Prefix"])
        if "ipv6Prefix" in prefix.keys():
            yield ipaddress.ip_network(prefix["ipv6Prefix"])


def icloud_data(provider: Provider) -> Iterator[IPNetwork]:
    """Get IP ranges used by iCloud Private Relay."""
    req = session.get(provider.url)
    req.raise_for_status()
    reader = csv.reader(line for line in req.text.split("\n") if line)
    for prefix, *_ in reader:
        yield ipaddress.ip_network(prefix)


def search_whois(net: IPNetwork, search_list: Iterable[str]) -> bool:
    """Searches for specific strings in the WHOIS data for a network.

    Only the description and name fields of the WHOIS result are compared
    to the search list. whois.toolforge.org does not support ranges,
    so results are obtained for the first address in the range.

    Search terms must be lowercase.
    """
    logger.debug(f"Searching WHOIS for {search_list} in {net}")
    url = f"{whois_api}/w/{net[0]}/lookup/json"
    try:
        req = session.get(url)
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


def not_blocked(
    net: IPNetwork, conn: pymysql.connections.Connection, exp_before: str = ""
) -> bool:
    """Query the database to determine if a range is currently blocked.

    Blocked ranges return False, unblocked ranges return True.
    Only sitewide blocks are considered, partial blocks are ignored.

    If exp_before is provided, blocks expiring before that date will be
    ignored (returns True).
    """
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

    db_args = dict(start=start, end=end, prefix=prefix)
    if exp_before:
        db_args["exp"] = exp_before

    if conn.db == b"centralauth_p":
        query = """
SELECT gb_id
FROM globalblocks
WHERE
    gb_range_start LIKE %(prefix)s
    AND gb_range_start <= %(start)s
    AND gb_range_end >= %(end)s
"""
        if exp_before:
            query += "AND (gb_expiry = 'infinity' OR gb_expiry >= %(exp)s)"
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
        if exp_before:
            query += "AND (ipb_expiry = 'infinity' OR ipb_expiry >= %(exp)s)"
    try:
        with conn.cursor() as cur:
            count = cur.execute(query, args=db_args)
            return count == 0
    except Exception as e:
        logger.exception(e)
        return False


def combine_ranges(all_ranges: Iterable[IPNetwork]) -> Iterator[IPNetwork]:
    """Sort ranges, split large ranges, and combine consecutive ranges.

    Ranges are sorted by IP version (4 before 6), then alphabetically.
    Adjacent ranges (with no gap between) are combined. Ranges larger than
    the default maximum rangeblock size (IPv4 /16, IPv6 /19) are split into
    ranges of that size or smaller.
    """
    # ipaddress.collapse_addresses can't handle v4 and v6 ranges at the same time
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


def make_section(provider: Provider, site_config: dict) -> str:
    """Prepares wikitext report section for a provider."""
    if provider.url:
        source = "[{0.url} {0.src}]".format(provider)
    elif provider.asn:
        source = ", ".join(f"[https://bgp.he.net/{asn} {asn}]" for asn in provider.asn)

    if provider.search:
        search = " for: " + ", ".join(provider.search)
    else:
        search = ""

    row = string.Template(site_config["row"])

    ranges = ""
    for net in provider.ranges:
        addr = str(net.network_address)
        # Convert 1-address ranges to that address
        if (net.version == 4 and net.prefixlen == 32) or (
            net.version == 6 and net.prefixlen == 128
        ):
            ip_range = addr
        else:
            ip_range = str(net)

        if provider.expiry:
            expiry = provider.expiry
        else:
            # Expiries are random, that way a bunch of blocks created at the
            # same time don't all expire at the same time.
            # The PRNG is seeded with the address and the year so that block
            # lengths are different between different addresses and different
            # blocks of the same address are suitably random, but do not change
            # daily. This keeps diffs readable.
            rand = random.Random(addr + str(datetime.date.today().year))
            expiry = f"{rand.randint(24, 36)} months"

        qs = urllib.parse.urlencode(
            {
                "wpExpiry": expiry,
                "wpHardBlock": 1,
                "wpReason": "other",
                "wpReason-other": string.Template(
                    site_config.get("block_reason", "")
                ).safe_substitute(blockname=provider.blockname),
            }
        )
        ranges += row.safe_substitute(
            ip_range=ip_range, addr=addr, name=provider.name, qs=qs
        )

    section = f"==={provider.name}===\nSearching {source}{search}\n{ranges}"
    return section


def make_mass_section(provider: Provider) -> str:
    """Prepares massblock-compatible report section for a provider."""
    section = f"\n==={provider.name}===\n" + "\n".join(
        str(net) for net in provider.ranges
    )
    return section


def update_page(
    new_text: str,
    title: str,
    mass: bool = False,
    exp: bool = False,
    total: Optional[int] = None,
) -> None:
    """Saves new report to the appropriate page."""
    title = "User:AntiCompositeBot/" + title
    if exp:
        title += "/expiring"
    if mass:
        title += "/mass"
    page = pywikibot.Page(site, title)
    # Replace everything below the Hosts header, but not above it
    top, sep, end = page.text.partition("== Hosts ==")
    text = top + new_text
    if total is None:
        summary = f"Updating report (Bot) (ASNBlock {__version__})"
    else:
        summary = f"Updating report: {total} ranges (Bot) (ASNBlock {__version__})"
    if simulate:
        logger.debug(f"Simulating {page.title(as_link=True)}: {summary}")
        logger.debug(text)
    else:
        utils.check_runpage(site, "ASNBlock")
        try:
            utils.save_page(
                text=text,
                page=page,
                summary=summary,
                bot=False,
                minor=False,
                mode="replace",
                force=False,
                new_ok=False,
                no_change_ok=True,
            )
        except Exception as e:
            logger.error("Page not saved, continuing", exc_info=e)


def collect_data(config: dict, db: str, exp_before: str = "") -> List[Provider]:
    """Collect IP address data for various hosting/proxy providers."""
    providers = [Provider(**provider) for provider in config["providers"]]
    rir_data = RIRData()
    ignore = {ipaddress.ip_network(net) for net in config["ignore"]}

    for provider in providers:
        logger.info(f"Checking ranges from {provider.name}")
        if provider.asn:
            ranges: Iterable[IPNetwork] = rir_data.get_asn_ranges(provider.asn.copy())
        elif provider.url:
            if "microsoft" in provider.url:
                ranges = microsoft_data()
            elif "google" in provider.url:
                ranges = google_data()
            elif "amazon" in provider.url:
                ranges = amazon_data(provider)
            elif "icloud" in provider.url:
                ranges = icloud_data(provider)
            else:
                logger.warning(f"{provider.name} has no handler")
                continue
        else:
            logger.warning(f"{provider.name} could not be processed")
            continue

        ranges = combine_ranges(ranges)

        conn = toolforge.connect(db, cluster="analytics")
        for net in ranges:
            if (
                net not in ignore
                and not_blocked(net, conn, exp_before)
                and (not provider.search or search_whois(net, provider.search))
            ):
                provider.ranges.append(net)
        conn.close()

    return providers


def provider_dict(items: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    """Prepare provider data for JSON dump"""
    output = {}
    for key, value in items:
        if key == "ranges":
            output[key] = [str(net) for net in value]
        else:
            output[key] = value
    return output


def main(db: str = "enwiki", days: int = 0) -> None:
    utils.check_runpage(site, "ASNBlock")
    logger.info("Loading configuration data")
    config = get_config()

    if days:
        exp_before = (
            datetime.datetime.utcnow() + datetime.timedelta(days=days)
        ).strftime("%Y%m%d%H%M%S")
    else:
        exp_before = ""

    providers = collect_data(config, db, exp_before)

    sites = cast(Dict[str, Dict[str, str]], config["sites"])
    site_config = sites.get(db, sites["enwiki"])
    title = "ASNBlock"
    if db == "enwiki":
        pass
    elif db == "centralauth":
        title += "/global"
    else:
        title += "/" + db

    total_ranges = sum(len(provider.ranges) for provider in providers)
    text = mass_text = "== Hosts ==\n"

    text += "".join(make_section(provider, site_config) for provider in providers)
    update_page(text, title=title, total=total_ranges, exp=bool(days))

    mass_text += "".join(make_mass_section(provider) for provider in providers)
    update_page(mass_text, title=title, mass=True, total=total_ranges, exp=bool(days))

    with open(
        f"/data/project/anticompositebot/www/static/{title.replace('/', '-')}.json", "w"
    ) as f:
        json.dump(
            [
                dataclasses.asdict(provider, dict_factory=provider_dict)
                for provider in providers
            ],
            f,
        )

    # logger.error("Finished")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("db")
    parser.add_argument(
        "--days", help="Ignore blocks expiring within this number of days", type=int
    )
    args = parser.parse_args()
    try:
        main(args.db, args.days)
    except Exception as e:
        logger.exception(e)
        raise
