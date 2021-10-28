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
import toolforge
import acnutils as utils
import requests
import csv
import ipaddress
import json
import urllib.parse
import string
import time
import random
import dataclasses
import datetime
import argparse
import concurrent.futures
import hashlib
from bs4 import BeautifulSoup  # type: ignore
import redis
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
    Set,
    Sequence,
)

__version__ = "2.0.3"

logger = utils.getInitLogger(
    "ASNBlock", level="VERBOSE", filename="stderr", thread=True
)

site = pywikibot.Site("en", "wikipedia")
simulate = False
session = requests.session()
session.headers[
    "User-Agent"
] = f"ASNBlock/{__version__} {toolforge.set_user_agent('anticompositebot')}"
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


class Target(NamedTuple):
    """A report target"""

    db: str
    days: str = ""

    def __repr__(self) -> str:
        if self.days:
            return f"{self.db}={self.days}"
        else:
            return self.db

    @classmethod
    def from_str(cls, target_str: str) -> "Target":
        db, _, days = target_str.partition("=")
        return cls(db, days)


@dataclasses.dataclass
class Provider:
    """Hosting provider or other network operator"""

    name: str
    blockname: str = ""
    asn: List[str] = dataclasses.field(default_factory=list)
    expiry: Union[str, Sequence[int]] = ""
    ranges: Dict[Target, List[IPNetwork]] = dataclasses.field(default_factory=dict)
    url: str = ""
    src: str = ""
    search: List[str] = dataclasses.field(default_factory=list)
    handler: str = ""
    block_reason: Union[str, Dict[str, str]] = ""

    def __post_init__(self) -> None:
        if not self.blockname:
            self.blockname = self.name
        if self.search:
            self.search = [entry.lower() for entry in self.search if entry]

    def get_ranges(
        self, config: "Config", targets: Iterable[Target]
    ) -> Dict[Target, List[IPNetwork]]:
        if self.asn:
            ranges: Iterable[IPNetwork] = ripestat_data(self)
        elif self.url or self.handler:
            ranges = URLHandler(self)
        else:
            logger.error(f"{self.name} could not be processed")
            return {}

        ranges = list(combine_ranges(ranges))
        logger.info(f"{self.name}: {len(ranges)} ranges to check")
        return filter_ranges(targets, ranges, self, config)


class Config(NamedTuple):
    providers: List[Provider]
    ignore: Set[IPNetwork]
    sites: Dict[str, Dict[str, str]]
    last_modified: datetime.datetime
    redis_prefix: str
    redis_host: str
    redis_port: int
    use_redis: bool
    workers: int

    @classmethod
    def load(cls) -> "Config":
        """Load configuration data from disk and the wiki"""
        private_config = utils.load_config("ASNBlock", __file__)
        page = pywikibot.Page(site, "User:AntiCompositeBot/ASNBlock/config.json")
        data = json.loads(page.text)
        data.update(private_config)

        return cls(
            redis_prefix=data.get("redis_prefix", ""),
            redis_host=data.get("redis_host", ""),
            redis_port=int(data.get("redis_port", "6379")),
            use_redis=data.get("use_redis", False),
            last_modified=page.editTime(),
            providers=[Provider(**provider) for provider in data["providers"]],
            ignore={ipaddress.ip_network(net) for net in data["ignore"]},
            sites=data["sites"],
            workers=data.get("workers", 3),
        )


class Cache:
    """Stores and retrieves data stored in Redis"""

    def __init__(self, config: Config, prefix_data: str) -> None:
        self._redis: Optional[redis.Redis] = None
        if config.redis_host and config.use_redis:
            logger.debug("Setting up Redis cache")
            self._redis = redis.Redis(host=config.redis_host, port=config.redis_port)
            self._prefix = (
                config.redis_prefix
                + "_"
                + hashlib.blake2b(bytes(prefix_data, encoding="utf-8")).hexdigest()
                + "_"
            )

    def __getitem__(
        self,
        key: str,
    ) -> Optional[bytes]:
        if not self._redis:
            return None
        return self._redis.get(self._prefix + key)

    def __setitem__(self, key: str, value: str) -> None:
        if self._redis:
            # Set a random TTL between 5 and 9 days from now, that way everything
            # doesn't expire on the same day. Then shorten that number by 12 hours so
            # nothing expires during a run or between enwiki and global.
            ttl = datetime.timedelta(days=7 + random.randint(-2, 2), hours=-12)
            self._redis.set(self._prefix + key, value, ex=ttl)

    def __delitem__(self, key: str) -> None:
        if self._redis:
            self._redis.delete(self._prefix + key)


def query_ripestat(api: str, catch: bool = True, /, **kwargs) -> dict:
    url = f"https://stat.ripe.net/data/{api}/data.json"
    params = {"sourceapp": "toolforge-anticompositebot-asnblock"}
    params.update(kwargs)
    try:
        req = session.get(url, params=params)
        req.raise_for_status()
        data = req.json()
    except Exception as err:
        if catch:
            logger.exception(err)
            data = {}
        else:
            raise err

    if data.get("status", "ok") != "ok":
        logger.error(f"RIPEStat error: {data.get('message')}")
    if not data.get("data_call_status", "supported").startswith("supported"):
        logger.warning(f"RIPEStat warning: {data['data_call_status']}")

    return data


def ripestat_data(provider: Provider) -> Iterator[IPNetwork]:
    # uses announced-prefixes API, which shows the prefixes the AS has announced
    # in the last two weeks. The ris-prefixes api also shows transiting prefixes.
    throttle = utils.Throttle(1)
    for asn in provider.asn:
        if not asn:
            continue
        throttle.throttle()
        data = query_ripestat("announced-prefixes", resource=asn)
        for prefix in data.get("data", {}).get("prefixes", []):
            yield ipaddress.ip_network(prefix["prefix"])


@dataclasses.dataclass
class URLHandler:
    provider: Provider

    def __iter__(self) -> Iterator[IPNetwork]:
        handler = None
        if self.provider.handler:
            handler = getattr(self, self.provider.handler, None)
        if not handler and self.provider.url:
            for name in vars(type(self)):
                if (not name.startswith("_")) and (name in self.provider.url):
                    handler = getattr(self, name, None)
                    break
        if handler is not None:
            yield from handler()
        else:
            logger.error(f"{self.provider.name} has no handler")
            yield from []

    def microsoft(self) -> Iterator[IPNetwork]:
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

    def amazon(self) -> Iterator[IPNetwork]:
        """Get IP ranges used by AWS."""
        req = session.get(self.provider.url)
        req.raise_for_status()
        data = req.json()
        for prefix in data["prefixes"]:
            yield ipaddress.IPv4Network(prefix["ip_prefix"])
        for prefix in data["ipv6_prefixes"]:
            yield ipaddress.IPv6Network(prefix["ipv6_prefix"])

    def google(self) -> Iterator[IPNetwork]:
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

    def icloud(self) -> Iterator[IPNetwork]:
        """Get IP ranges used by iCloud Private Relay."""
        req = session.get(self.provider.url)
        req.raise_for_status()
        reader = csv.reader(line for line in req.text.split("\n") if line)
        for prefix, *_ in reader:
            try:
                yield ipaddress.ip_network(prefix)
            except ValueError as e:
                logger.warning("Invalid IP network in iCloud data", exc_info=e)
                continue

    def oracle(self) -> Iterator[IPNetwork]:
        """Get IP ranges used by Oracle Cloud Infrastructure."""
        req = session.get(self.provider.url)
        req.raise_for_status()
        data = req.json()
        for region in data["regions"]:
            for cidr in region["cidrs"]:
                yield ipaddress.ip_network(cidr["cidr"])


def search_toolforge_whois(
    net: IPNetwork,
    search_list: Iterable[str],
    throttle: Optional[utils.Throttle] = None,
) -> Optional[bool]:
    """Searches for specific strings in the WHOIS data for a network.

    Returns true if any of the search terms are included in the name or
    description of the WHOIS data. whois.toolforge.org does not support ranges,
    so results are obtained for the first address in the range.

    Search terms must be lowercase.
    """
    logger.debug(f"Searching WHOIS for {search_list} in {net}")
    if throttle:
        throttle.throttle()
    url = f"{whois_api}/w/{net[0]}/lookup/json"
    try:
        req = session.get(url)
        if req.status_code == 429:
            logger.warning(f"429: Too many requests on {url}")
            time.sleep(60)
            req = session.get(url)
        req.raise_for_status()
        for whois_net in req.json()["nets"]:
            name = str(whois_net.get("name", "")).lower()
            desc = str(whois_net.get("description", "")).lower()
            for search in search_list:
                if search in name or search in desc:
                    return True
    except requests.exceptions.HTTPError as e:
        logger.warning(e, exc_info=True)
        return None
    except Exception as e:
        logger.warning(e, exc_info=True)
        return None
    return False


def search_ripestat_whois(
    net: IPNetwork,
    search_list: Iterable[str],
    throttle: Optional[utils.Throttle] = None,
) -> Optional[bool]:
    logger.debug(f"Searching RIPEStat WHOIS for {search_list} in {net}")
    if throttle:
        throttle.throttle()

    try:
        data = query_ripestat("whois", False, resource=str(net[0])).get("data", {})
    except requests.exceptions.HTTPError as e:
        logger.warning(e, exc_info=True)
        return None
    except Exception as e:
        logger.exception(e)
        return None

    for record in data.get("records", []):
        for entry in record:
            if entry.get("key") in {"descr", "netname"}:
                val = entry.get("value", "").lower()
                for search in search_list:
                    if search in val:
                        return True
    return False


def cache_search_whois(
    net: IPNetwork,
    search_list: Iterable[str],
    cache: Cache,
    throttle: Optional[utils.Throttle] = None,
) -> bool:
    """Wrapper around search_whois to check for a cached result first"""
    cached = cache[str(net)]
    if cached is not None:
        logger.debug(f"Cached WHOIS for {net}: {bool(cached)}")
        return bool(cached)

    # seed the rng so that the same net always gets the same WHOIS source
    rand = random.Random(str(net))
    func = rand.choices(
        [search_toolforge_whois, search_ripestat_whois], weights=[40, 60]
    )[0]
    result = func(net, search_list, throttle=throttle)
    if result is not None:
        cache[str(net)] = "1" if result else ""
    return bool(result)


def db_network(net: IPNetwork) -> Dict[str, str]:
    """Converts an IPNetwork to the format MediaWiki uses to store rangeblocks.

    Returns a dict with keys "start", "end", and "prefix"
    """
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
    else:  # pragma: no cover
        raise ValueError(net)

    return dict(start=start, end=end, prefix=prefix)


def query_blocks(net: IPNetwork, db: str) -> str:
    """Query the database to determine if a range is currently blocked.

    Blocked ranges return False, unblocked ranges return True.
    Only sitewide blocks are considered, partial blocks are ignored.

    If exp_before is provided, blocks expiring before that date will be
    ignored (returns True).
    """
    logger.debug(f"Checking for blocks on {net}")

    db_args = db_network(net)

    if db.startswith("centralauth"):
        query = """
SELECT gb_expiry
FROM globalblocks
WHERE
    gb_range_start LIKE %(prefix)s
    AND gb_range_start <= %(start)s
    AND gb_range_end >= %(end)s
"""
    else:
        query = """
SELECT ipb_expiry
FROM ipblocks_ipindex
WHERE
    ipb_range_start LIKE %(prefix)s
    AND ipb_range_start <= %(start)s
    AND ipb_range_end >= %(end)s
    AND ipb_sitewide = 1
    AND ipb_auto = 0
"""
    try:
        with toolforge.connect(db, cluster="analytics") as conn:  # type: ignore
            with conn.cursor() as cur:
                count = cur.execute(query, args=db_args)
                if count > 0:
                    return str(cur.fetchall()[0][0], encoding="utf-8")
                else:
                    return ""

    except Exception as e:
        logger.exception(e)
        return ""


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


def get_expiry(addr: str, provider: Provider, site_config: dict) -> str:
    # first check if there's a provider override
    for raw_exp in [provider.expiry, site_config.get("expiry")]:
        if raw_exp:
            if isinstance(raw_exp, str):
                # constant expiry, just return that
                return raw_exp
            elif len(raw_exp) == 2:
                exp_range = raw_exp
                break
            else:
                logger.error(f"{raw_exp} is not a valid expiry for {provider.name}")
    else:
        exp_range = [24, 36]

    # Expiries are random by default, that way a bunch of blocks created at the
    # same time don't all expire at the same time.  The PRNG is seeded with the
    # address and the year so that block lengths are different between
    # different addresses and different blocks of the same address are suitably
    # random, but do not change daily. This keeps diffs readable.
    rand = random.Random(addr + str(datetime.date.today().year))
    return f"{rand.randint(*exp_range)} months"


def make_section(provider: Provider, site_config: dict, target: Target) -> str:
    """Prepares wikitext report section for a provider."""
    if provider.url:
        source = "[{0.url} {0.src}]".format(provider)
    elif provider.asn:  # pragma: no branch
        source = ", ".join(f"[https://bgp.he.net/{asn} {asn}]" for asn in provider.asn)

    if provider.search:
        search = " for: " + ", ".join(provider.search)
    else:
        search = ""

    row = string.Template(site_config["row"])

    ranges = ""
    for net in provider.ranges.get(target, []):
        addr = str(net.network_address)
        # Convert 1-address ranges to that address
        if (net.version == 4 and net.prefixlen == 32) or (
            net.version == 6 and net.prefixlen == 128
        ):
            ip_range = addr
        else:
            ip_range = str(net)

        if isinstance(provider.block_reason, str) and provider.block_reason:
            block_reason = provider.block_reason
        elif (
            isinstance(provider.block_reason, dict)
            and target.db in provider.block_reason
        ):
            block_reason = provider.block_reason[target.db]
        else:
            block_reason = site_config.get("block_reason", "")
        qs = urllib.parse.urlencode(
            {
                "wpExpiry": get_expiry(addr, provider, site_config),
                "wpHardBlock": 1,
                "wpReason": "other",
                "wpReason-other": string.Template(block_reason).safe_substitute(
                    blockname=provider.blockname
                ),
            }
        )
        ranges += row.safe_substitute(
            ip_range=ip_range, addr=addr, name=provider.name, qs=qs
        )

    count = f" ({len(provider.ranges.get(target, []))})" if ranges else ""
    section = f"==={provider.name}{count}===\nSearching {source}{search}\n{ranges}"
    return section


def make_mass_section(provider: Provider, target: Target) -> str:
    """Prepares massblock-compatible report section for a provider."""
    section = f"\n==={provider.name}===\n" + "\n".join(
        str(net) for net in provider.ranges.get(target, [])
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
        utils.check_runpage(site, task="ASNBlock")
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


def unblocked_or_expiring(expiry: str, days: str, now: datetime.datetime) -> bool:
    # True: unblocked or expiring before days
    # False: Blocked
    if not expiry:
        # Not blocked
        return True
    elif expiry == "infinity":
        # Blocked indef, not going to expire
        return False
    elif not days:
        # Target doesn't care about expiring blocks
        return False
    elif datetime.datetime.strptime(expiry, "%Y%m%d%H%M%S") - now >= datetime.timedelta(
        days=int(days)
    ):
        return False
    else:
        return True


def get_blocks(
    net: IPNetwork,
    db: str,
    targets: Iterable[Target],
    now: datetime.datetime,
    config: Config,
) -> List[Target]:
    if net in config.ignore:
        return []
    expiry = query_blocks(net, db)
    return [
        target for target in targets if unblocked_or_expiring(expiry, target.days, now)
    ]


def filter_ranges(
    targets: Iterable[Target],
    ranges: List[IPNetwork],
    provider: Provider,
    config: Config,
) -> Dict[Target, List[IPNetwork]]:
    """Filter a list of IP ranges based on block status and WHOIS data.

    Returns a dict mapping targets to lists of unblocked ranges
    """
    if not ranges:
        return {}

    cache = Cache(config, ",".join(provider.search))
    throttle = utils.Throttle(1.5)
    filtered: Dict[IPNetwork, List[Target]] = {}
    now = datetime.datetime.utcnow()

    # Group targets with the same db
    dbs: Dict[str, List[Target]] = {}
    for target in targets:
        dbs.setdefault(target.db, []).append(target)

    for db, targets in dbs.items():
        logger.debug(f"Checking blocks in {targets}")
        logger.debug(f"{len(ranges)}, {db}")

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=config.workers
        ) as executor:
            future_blocks = {
                executor.submit(get_blocks, net, db, targets, now, config): net
                for net in ranges
            }
            for future in concurrent.futures.as_completed(future_blocks):
                net = future_blocks[future]
                filtered.setdefault(net, []).extend(future.result())

    inverted: Dict[Target, List[IPNetwork]] = {}
    for net in sorted(filtered, key=ipaddress.get_mixed_type_key):  # type: ignore
        blocks = filtered[net]
        if not provider.search or cache_search_whois(
            net, provider.search, cache, throttle=throttle
        ):
            for target in blocks:
                inverted.setdefault(target, []).append(net)

    return inverted


def collect_data(config: Config, targets: Iterable[Target]) -> List[Provider]:
    """Collect IP address data for various hosting/proxy providers."""
    providers = config.providers
    tot = len(providers)
    logger.info(f"Loaded {tot} providers")

    for i, provider in enumerate(providers, start=1):
        logger.info(f"Checking ranges from {provider.name} ({i}/{tot})")
        provider.ranges = provider.get_ranges(config, targets)

    return providers


def provider_dict(items: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    """Prepare provider data for JSON dump"""
    output = {}
    for key, value in items:
        if key == "ranges":
            output[key] = {
                str(target): [str(net) for net in nets]
                for target, nets in value.items()
            }
        else:
            output[key] = value
    return output


def dump_report(title: str, providers: Iterable[Provider]) -> None:
    with open(
        f"/data/project/anticompositebot/www/static/{title.replace('/', '-')}.json",
        "w",
    ) as f:
        json.dump(
            [
                dataclasses.asdict(provider, dict_factory=provider_dict)
                for provider in providers
            ],
            f,
        )


def main(target_strs: List[str]) -> None:
    utils.check_runpage(site, task="ASNBlock")
    start_time = time.monotonic()
    logger.info(f"ASNBlock {__version__} starting up, Loading configuration data")
    config = Config.load()
    targets = tuple(Target.from_str(target) for target in target_strs)

    providers = collect_data(config, targets)

    sites = config.sites
    for target in targets:
        site_config = sites.get(target.db, sites["enwiki"])
        title = "ASNBlock"
        if target.db == "enwiki":
            pass
        elif target.db == "centralauth":
            title += "/global"
        else:
            title += "/" + target.db

        total_ranges = sum(
            len(provider.ranges.get(target, [])) for provider in providers
        )
        total_time = str(datetime.timedelta(seconds=int(time.monotonic() - start_time)))
        update_time = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
        text = mass_text = f"== Hosts ==\nLast updated {update_time} in {total_time}.\n"

        text += "\n".join(
            make_section(provider, site_config, target) for provider in providers
        )
        update_page(text, title=title, total=total_ranges, exp=bool(target.days))

        mass_text += "".join(
            make_mass_section(provider, target) for provider in providers
        )
        update_page(
            mass_text, title=title, mass=True, total=total_ranges, exp=bool(target.days)
        )

        dump_report(title, providers)

    logger.info("Finished")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", nargs="+")
    args = parser.parse_args()
    try:
        main(args.targets)
    except Exception as e:
        logger.exception(e)
        raise
