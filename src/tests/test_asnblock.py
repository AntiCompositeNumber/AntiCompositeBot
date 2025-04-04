#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2021 AntiCompositeNumber

import os
import sys
import pytest
import unittest.mock as mock
import ipaddress
import datetime
import requests
import urllib.parse
import time
import random
import string
import base64
import yaml
import acnutils as utils

sys.path.append(os.path.realpath(os.path.dirname(__file__) + "/.."))
os.environ["LOG_FILE"] = "stderr"
import asnblock  # noqa: E402

session = asnblock.session


@pytest.mark.parametrize(
    "target,db,days,to_str",
    [
        (asnblock.Target("enwiki"), "enwiki", "", "enwiki"),
        (asnblock.Target("enwiki", "30"), "enwiki", "30", "enwiki=30"),
        (asnblock.Target("centralauth", ""), "centralauth", "", "centralauth"),
        (asnblock.Target("centralauth", "30"), "centralauth", "30", "centralauth=30"),
        (asnblock.Target.from_str("enwiki"), "enwiki", "", "enwiki"),
        (asnblock.Target.from_str("centralauth"), "centralauth", "", "centralauth"),
        (asnblock.Target.from_str("enwiki=30"), "enwiki", "30", "enwiki=30"),
        (
            asnblock.Target.from_str("centralauth=30"),
            "centralauth",
            "30",
            "centralauth=30",
        ),
    ],
)
def test_target(target, db, days, to_str):
    assert isinstance(target, asnblock.Target)
    assert target.db == db
    assert target.days == days
    assert str(target) == to_str


def test_provider():
    prov = asnblock.Provider(name="Name", search=["foo", "BAR"])
    assert prov.blockname == "Name"
    assert prov.search == ["foo", "bar"]


def test_provider_empty():
    prov = asnblock.Provider(name="Name", blockname="blockname")
    assert prov.name == "Name"
    assert prov.blockname == "blockname"
    assert prov.search == []


@pytest.fixture(scope="module")
def live_config():
    return asnblock.Config.load()


def test_get_config(live_config):
    assert live_config.providers
    assert live_config.ignore
    assert live_config.sites


@pytest.mark.skip("Not implemented")
def test_cache():
    pass


@pytest.fixture(scope="module")
def wmf_provider():
    return asnblock.Provider(
        name="Wikimedia Foundation", asn=["AS14907", "43821"], search=["wikimedia"]
    )


@pytest.fixture(scope="module")
def wmf_ripestat_ranges(wmf_provider):
    return set(asnblock.ripestat_data(wmf_provider))


def test_ripestat_data(wmf_ripestat_ranges):
    res = session.get(
        "https://gerrit.wikimedia.org/r/plugins/gitiles/operations/homer/public/"
        "+/refs/heads/master/config/sites.yaml?format=TEXT"
    )
    res.raise_for_status()
    sites = yaml.safe_load(base64.b64decode(res.text))
    called_once = False
    for site in sites.values():
        for net in site.get("bgp_out", {}):
            called_once = True
            assert ipaddress.ip_network(net) in wmf_ripestat_ranges
        for net in site.get("bgp6_out", {}):
            called_once = True
            assert ipaddress.ip_network(net) in wmf_ripestat_ranges
    assert called_once


def test_ripestat_data_raise(wmf_provider):
    mock_get = mock.Mock(spec=session.get)
    mock_req = mock_get.return_value
    mock_req.raise_for_status.side_effect = requests.exceptions.HTTPError
    with mock.patch("asnblock.session.get", mock_get):
        assert list(asnblock.ripestat_data(wmf_provider)) == []

    mock_get.assert_called()


@pytest.mark.parametrize(
    "search",
    [
        name
        for name in vars(asnblock.URLHandler)
        if not (name.startswith("_") or name == "microsoft")
    ],
)
def test_URLHandler(search, live_config):
    provider = next(filter(lambda p: search in p.url, live_config.providers))
    ranges = asnblock.URLHandler(provider)

    once = False
    for prefix in ranges:
        assert isinstance(prefix, ipaddress.IPv4Network) or isinstance(
            prefix, ipaddress.IPv6Network
        )
        once = True

    assert once is True


@pytest.mark.parametrize(
    "whois", [asnblock.search_toolforge_whois, asnblock.search_ripestat_whois]
)
@pytest.mark.parametrize(
    "net,expected",
    [
        (ipaddress.ip_network("198.35.26.0/23"), True),
        (ipaddress.ip_network("2620:0:860::/46"), True),
        (ipaddress.ip_network("8.8.8.8/32"), False),
    ],
)
@pytest.mark.parametrize("search", ["wikimedia", "foundation"])
@pytest.mark.skipif(
    session.head(asnblock.whois_api).status_code == 503,
    reason="Toolforge whois is down",
)
def test_search_toolforge_whois(whois, net, expected, search):
    throttle = mock.Mock(spec=utils.Throttle)
    assert asnblock.search_toolforge_whois(net, [search], throttle=throttle) is expected
    throttle.throttle.assert_called_once()


def test_search_toolforge_whois_exception():
    mock_session = mock.Mock()
    mock_session.get.return_value.raise_for_status.side_effect = (
        requests.exceptions.HTTPError
    )
    with mock.patch("asnblock.session", mock_session):
        assert (
            asnblock.search_toolforge_whois(ipaddress.ip_network("127.0.0.1/32"), [""])
            is None
        )


@pytest.fixture
def mock_cache():
    cache = mock.MagicMock(spec=asnblock.Cache)
    cache_dict = {}

    def getitem(key):
        val = cache_dict.get(key)
        if val is not None:
            return bytes(val, encoding="utf-8")
        else:
            return None

    def setitem(key, value):
        cache_dict[key] = value

    cache.__getitem__.side_effect = getitem
    cache.__setitem__.side_effect = setitem
    return cache


@pytest.mark.parametrize(
    "net,expected",
    [
        (ipaddress.ip_network("198.35.26.0/23"), True),
        (ipaddress.ip_network("2620:0:860::/46"), True),
        (ipaddress.ip_network("8.8.8.8/32"), False),
    ],
)
def test_cache_search_whois(net, expected, mock_cache):
    search = ["Wikimedia"]
    mock_search = mock.Mock(return_value=expected)
    mock_throttle = mock.Mock(spec=utils.Throttle)
    with mock.patch.multiple(
        "asnblock",
        search_toolforge_whois=mock_search,
        search_ripestat_whois=mock_search,
    ):
        res = asnblock.cache_search_whois(
            net, search, mock_cache, throttle=mock_throttle
        )
        # First request, should not be cached, should call search_whois
        assert res is expected
        mock_search.assert_called_once_with(net, search, throttle=mock_throttle)

        # Second request, should be cached, should not call search_whois
        cache_res = asnblock.cache_search_whois(
            net, search, mock_cache, throttle=mock_throttle
        )
        assert cache_res is expected
        mock_search.assert_called_once()
        mock_throttle.throttle.assert_not_called()


@pytest.mark.parametrize(
    "net,expected",
    [
        (
            ipaddress.ip_network("204.157.102.0/24"),
            dict(start="CC9D6600", prefix="CC9D%", end="CC9D66FF"),
        ),
        (
            ipaddress.ip_network("191.156.0.0/16"),
            dict(start="BF9C0000", prefix="BF9C%", end="BF9CFFFF"),
        ),
        (
            ipaddress.ip_network("2A0D:A300:0:0:0:0:0:0/29"),
            dict(
                start="v6-2A0DA300000000000000000000000000",
                prefix="v6-2A0D%",
                end="v6-2A0DA307FFFFFFFFFFFFFFFFFFFFFFFF",
            ),
        ),
        (
            ipaddress.ip_network("2A01:B747:0:0:0:0:0:0/32"),
            dict(
                start="v6-2A01B747000000000000000000000000",
                prefix="v6-2A01%",
                end="v6-2A01B747FFFFFFFFFFFFFFFFFFFFFFFF",
            ),
        ),
    ],
)
def test_db_network(net, expected):
    result = asnblock.db_network(net)
    assert expected == result


@pytest.mark.skip("Not implemented")
def test_query_blocks():
    pass


@pytest.mark.skip("Not implemented")
def test_get_blocks():
    pass


def test_combine_ranges():
    ranges = [
        ipaddress.IPv6Network("2a04:4e41:2f:1::/64"),
        ipaddress.IPv4Network("146.75.195.14/31"),
        ipaddress.IPv4Network("146.75.195.16/31"),
        ipaddress.IPv4Network("146.75.195.26/31"),
        ipaddress.IPv4Network("146.75.195.20/31"),
        ipaddress.IPv6Network("2a04:4e41:2f:9::/64"),
        ipaddress.IPv4Network("146.75.195.8/31"),
        ipaddress.IPv4Network("146.75.195.0/31"),
        ipaddress.IPv6Network("2a04:4e41:2f:c::/64"),
        ipaddress.IPv6Network("2a04:4e41:2f:8::/64"),
        ipaddress.IPv6Network("2a04:4e41:2f:e::/64"),
        ipaddress.IPv4Network("146.75.195.18/31"),
        ipaddress.IPv4Network("146.75.195.10/31"),
        ipaddress.IPv6Network("2a04:4e41:2f:2::/64"),
        ipaddress.IPv6Network("2a04:4e41:2f:6::/64"),
        ipaddress.IPv6Network("2a04:4e41:2f:f::/64"),
        ipaddress.IPv4Network("146.75.195.4/31"),
        ipaddress.IPv6Network("2a04:4e41:2f:a::/64"),
        ipaddress.IPv6Network("fd00::/16"),
        ipaddress.IPv6Network("2a04:4e41:2f:3::/64"),
        ipaddress.IPv4Network("146.75.195.22/31"),
        ipaddress.IPv4Network("146.75.195.24/31"),
        ipaddress.IPv6Network("2a04:4e41:2f:d::/64"),
        ipaddress.IPv4Network("146.75.195.6/31"),
        ipaddress.IPv6Network("2a04:4e41:2f::/64"),
        ipaddress.IPv4Network("146.75.195.32/31"),
        ipaddress.IPv4Network("146.75.195.2/31"),
        ipaddress.IPv4Network("146.75.195.28/31"),
        ipaddress.IPv4Network("146.75.195.12/31"),
        ipaddress.IPv4Network("146.75.195.30/31"),
        ipaddress.IPv6Network("2a04:4e41:2f:7::/64"),
        ipaddress.IPv4Network("10.0.0.0/13"),
        ipaddress.IPv6Network("2a04:4e41:2f:4::/64"),
        ipaddress.IPv6Network("2a04:4e41:2f:5::/64"),
        ipaddress.IPv6Network("2a04:4e41:2f:b::/64"),
    ]
    expected = [
        ipaddress.IPv4Network("10.0.0.0/16"),
        ipaddress.IPv4Network("10.1.0.0/16"),
        ipaddress.IPv4Network("10.2.0.0/16"),
        ipaddress.IPv4Network("10.3.0.0/16"),
        ipaddress.IPv4Network("10.4.0.0/16"),
        ipaddress.IPv4Network("10.5.0.0/16"),
        ipaddress.IPv4Network("10.6.0.0/16"),
        ipaddress.IPv4Network("10.7.0.0/16"),
        ipaddress.IPv4Network("146.75.195.0/27"),
        ipaddress.IPv4Network("146.75.195.32/31"),
        ipaddress.IPv6Network("2a04:4e41:2f::/60"),
        ipaddress.IPv6Network("fd00::/19"),
        ipaddress.IPv6Network("fd00:2000::/19"),
        ipaddress.IPv6Network("fd00:4000::/19"),
        ipaddress.IPv6Network("fd00:6000::/19"),
        ipaddress.IPv6Network("fd00:8000::/19"),
        ipaddress.IPv6Network("fd00:a000::/19"),
        ipaddress.IPv6Network("fd00:c000::/19"),
        ipaddress.IPv6Network("fd00:e000::/19"),
    ]

    assert list(asnblock.combine_ranges(ranges)) == expected


@pytest.mark.parametrize(
    "prov_expiry, site_expiry, expected",
    [
        ("", "", (24, 36)),
        ("", None, (24, 36)),
        ([10, 12], "", (10, 12)),
        ([10, 12], None, (10, 12)),
        ("", [14, 16], (14, 16)),
        ("31 hours", "", "31 hours"),
        ("31 hours", None, "31 hours"),
        ("", "72 hours", "72 hours"),
        ([10, 12], [18, 20], (10, 12)),
        ([10, 12], "72 hours", (10, 12)),
    ],
)
def test_get_expiry(prov_expiry, site_expiry, expected):
    site_config = {}
    if site_expiry is not None:
        site_config["expiry"] = site_expiry
    provider = asnblock.Provider("foo", expiry=prov_expiry)

    result = asnblock.get_expiry("", provider, site_config)

    if isinstance(expected, tuple):
        val = int(result.replace(" months", ""))
        assert val >= expected[0]
        assert val <= expected[1]
    else:
        assert result == expected


@pytest.mark.parametrize(
    "provider,asserts",
    [
        (
            asnblock.Provider(
                name="chocolate",
                asn=["AS9876"],
                search=["banana", "coffee"],
            ),
            ["chocolate", "banana", "coffee", "AS9876"],
        ),
        (
            asnblock.Provider(
                name="chocolate",
                url="http://example.com/coffee",
                src="banana",
            ),
            ["chocolate", "banana", "coffee"],
        ),
        (
            asnblock.Provider(
                name="chocolate",
                asn=["AS9876"],
                search=["banana", "coffee"],
                block_reason="oreo",
                expiry="25 months",
            ),
            ["chocolate", "banana", "coffee"],
        ),
        (
            asnblock.Provider(
                name="chocolate",
                asn=["AS9876"],
                search=["banana", "coffee"],
                block_reason={"enwiki": "oreo", "centralauth": "spinach"},
                expiry=[28, 34],
            ),
            ["chocolate", "banana", "coffee"],
        ),
    ],
)
def test_make_section(provider, asserts, live_config):
    provider.ranges = {
        asnblock.Target("enwiki"): [
            ipaddress.IPv4Network("10.0.0.0/16"),
            ipaddress.IPv4Network("10.1.0.0/32"),
            ipaddress.IPv6Network("fd00::/19"),
            ipaddress.IPv6Network("fd00:2000::/128"),
        ],
        asnblock.Target("enwiki", "30"): [
            ipaddress.IPv4Network("10.1.0.0/32"),
        ],
        asnblock.Target("centralauth"): [
            ipaddress.IPv6Network("fd00::/19"),
            ipaddress.IPv6Network("fd00:3000::/128"),
        ],
    }
    site_config = live_config.sites["enwiki"]

    mock_subst = mock.Mock(return_value="")
    mock_template = mock.Mock(spec=string.Template)
    mock_template.return_value.safe_substitute = mock_subst
    with mock.patch("string.Template", mock_template):
        section = asnblock.make_section(
            provider, site_config, asnblock.Target("enwiki")
        )

    for statement in asserts:
        assert statement in section

    ranges = [
        "fd00:2000::",
        "fd00::/19",
        "10.1.0.0",
        "10.0.0.0/16",
    ]
    expiries = set()
    if provider.block_reason:
        mock_template.assert_any_call("oreo")
    mock_subst.assert_called()

    for name, args, kwargs in mock_subst.mock_calls:
        assert not args
        # string.Template is used in 2 places, to fill the block reason
        # and to make the section itself.
        if "blockname" in kwargs:
            assert kwargs["blockname"] == "chocolate"
            continue

        assert kwargs["name"] == "chocolate"
        assert kwargs["ip_range"].startswith(kwargs["addr"])
        ranges.remove(kwargs["ip_range"])
        qs = urllib.parse.parse_qs(kwargs["qs"])
        assert qs["wpHardBlock"] == ["1"]
        assert qs["wpReason"] == ["other"]
        exp = int(qs["wpExpiry"][0].replace(" months", ""))
        assert (exp >= 24) and (exp <= 36)
        expiries.add(exp)

    # Occasionally two of the expiries will be the same, because random
    assert len(expiries) >= 3 if not isinstance(provider.expiry, str) else 1


@pytest.mark.parametrize(
    "provider,asserts",
    [
        (
            asnblock.Provider(
                name="chocolate",
                asn=["AS9876"],
                search=["banana", "coffee"],
            ),
            ["chocolate", "banana", "coffee", "AS9876", "Colocationwebhost"],
        ),
        (
            asnblock.Provider(
                name="chocolate",
                url="http://example.com/coffee",
                src="banana",
            ),
            ["chocolate", "banana", "coffee", "example.com", "Colocationwebhost"],
        ),
        (
            asnblock.Provider(
                name="chocolate",
                asn=["AS9876"],
                search=["banana", "coffee"],
                block_reason="oreo <!-- $blockname -->",
                blockname="mint",
                expiry="25 months",
            ),
            ["chocolate", "banana", "coffee", "oreo", "25+months"],
        ),
        (
            asnblock.Provider(
                name="chocolate",
                asn=["AS9876"],
                search=["banana", "coffee"],
                blockname="mint",
                block_reason={
                    "enwiki": "oreo <!-- $blockname -->",
                    "centralauth": "spinach",
                },
                expiry=[28, 34],
            ),
            ["chocolate", "banana", "coffee", "oreo", "mint"],
        ),
    ],
)
def test_make_section_nomock(provider, asserts, live_config):
    provider.ranges = {
        asnblock.Target("enwiki"): [
            ipaddress.IPv4Network("10.0.0.0/16"),
            ipaddress.IPv4Network("10.1.0.0/32"),
            ipaddress.IPv6Network("fd00::/19"),
            ipaddress.IPv6Network("fd00:2000::/128"),
        ],
        asnblock.Target("enwiki", "30"): [
            ipaddress.IPv4Network("10.1.0.0/32"),
        ],
        asnblock.Target("centralauth"): [
            ipaddress.IPv6Network("fd00::/19"),
            ipaddress.IPv6Network("fd00:3000::/128"),
        ],
    }
    site_config = live_config.sites["enwiki"]

    section = asnblock.make_section(provider, site_config, asnblock.Target("enwiki"))

    for statement in asserts:
        assert statement in section
    assert "spinach" not in section


def test_make_mass_section():
    provider = asnblock.Provider(
        name="chocolate",
        asn=["AS9876"],
        search=["banana", "coffee"],
        ranges={
            asnblock.Target("enwiki"): [
                ipaddress.IPv4Network("10.0.0.0/16"),
                ipaddress.IPv4Network("10.1.0.0/32"),
                ipaddress.IPv6Network("fd00::/19"),
                ipaddress.IPv6Network("fd00:2000::/128"),
            ],
            asnblock.Target("enwiki", "30"): [
                ipaddress.IPv4Network("10.1.0.0/32"),
            ],
            asnblock.Target("centralauth"): [
                ipaddress.IPv6Network("fd00::/19"),
                ipaddress.IPv6Network("fd00:3000::/128"),
            ],
        },
    )
    target = asnblock.Target("enwiki")

    section = asnblock.make_mass_section(provider, target)

    assert provider.name in section
    assert len(section.split()) == 5


@pytest.mark.skip("Not implemented")
def test_update_page():
    pass


@pytest.mark.parametrize(
    "expiry,days,expected",
    [
        (40, "30", False),
        (40, "", False),
        (20, "30", True),
        (20, "", False),
        ("infinity", "30", False),
        ("infinity", "", False),
        ("", "30", True),
        ("", "", True),
    ],
)
def test_unblocked_or_expiring(expiry, days, expected):
    now = datetime.datetime.utcnow()
    if isinstance(expiry, int):
        expiry = (now + datetime.timedelta(days=int(expiry))).strftime("%Y%m%d%H%M%S")
    result = asnblock.unblocked_or_expiring(expiry, days, now)
    assert result is expected


def mock_filter_ranges(targets, ranges, provider, config):
    return {targets[0]: ranges.copy()}


def fuzz_side_effect(*args, **kwargs):
    time.sleep(random.random())
    return mock.DEFAULT


@pytest.mark.parametrize(
    "ranges",
    [
        [
            ipaddress.ip_network("91.198.174.0/24"),
            ipaddress.ip_network("103.102.166.0/24"),
            ipaddress.ip_network("185.15.56.0/22"),
            ipaddress.ip_network("185.71.138.0/24"),
            ipaddress.ip_network("198.35.26.0/23"),
            ipaddress.ip_network("208.80.152.0/22"),
            ipaddress.ip_network("2001:df2:e500::/48"),
            ipaddress.ip_network("2620:0:860::/46"),
            ipaddress.ip_network("2a02:ec80::/32"),
        ],
        [],
    ],
)
def test_filter_ranges(ranges, wmf_provider, live_config):
    targets = (asnblock.Target("enwiki"), asnblock.Target("enwiki", "30"))
    config = live_config

    mock_get_blocks = mock.Mock()
    mock_get_blocks.side_effect = fuzz_side_effect
    mock_get_blocks.return_value = list(targets)
    mock_search = mock.Mock(return_value=True)

    with mock.patch.multiple(
        "asnblock", get_blocks=mock_get_blocks, cache_search_whois=mock_search
    ):
        result = asnblock.filter_ranges(targets, ranges, wmf_provider, config)

    mock_get_blocks.assert_has_calls(
        [mock.call(net, "enwiki", list(targets), mock.ANY, config) for net in ranges],
        any_order=True,
    )
    assert mock_search.call_count == len(ranges)
    for target in targets:
        assert result.get(target, []) == ranges


@pytest.mark.parametrize(
    "datasource,provider",
    [
        (
            "ripestat_data",
            asnblock.Provider(
                name="DigitalOcean",
                blockname="DigitalOcean",
                asn=["AS14061"],
                expiry="",
                ranges={},
                url="",
                src="",
                search=[
                    "digitalocean",
                    "serverstack",
                    "digital ocean",
                    "vpn",
                    "colocation",
                    "heficed",
                ],
            ),
        ),
        (
            "microsoft",
            asnblock.Provider(
                name="Microsoft Azure",
                blockname="Microsoft Azure",
                asn=[],
                expiry="",
                ranges={},
                url="https://www.microsoft.com/en-us/download/details.aspx?id=56519",
                src="azure ranges",
                search=[],
            ),
        ),
        (
            "google",
            asnblock.Provider(
                name="Google Cloud",
                blockname="Google Cloud",
                asn=[],
                expiry="",
                ranges={},
                url="https://cloud.google.com/compute/docs/faq#find_ip_range",
                src="google ranges",
                search=[],
            ),
        ),
        (
            "amazon",
            asnblock.Provider(
                name="Amazon Web Services",
                blockname="Amazon Web Services",
                asn=[],
                expiry="",
                ranges={},
                url="https://ip-ranges.amazonaws.com/ip-ranges.json",
                src="amazon ranges",
                search=[],
            ),
        ),
        (
            "amazon",
            asnblock.Provider(
                name="Amazon Web Services",
                blockname="Amazon Web Services",
                asn=[],
                expiry="",
                ranges={},
                url="https://ip-ranges.amazonaws.com/ip-ranges.json",
                src="amazon ranges",
                search=[],
                handler="amazon",
            ),
        ),
        (
            "icloud",
            asnblock.Provider(
                name="iCloud Private Relay",
                blockname="iCloud Private Relay",
                asn=[],
                expiry="",
                ranges={},
                url="https://mask-api.icloud.com/egress-ip-ranges.csv",
                src="iCloud ranges",
                search=[],
            ),
        ),
        (
            "oracle",
            asnblock.Provider(
                name="Oracle Cloud Infrastructure",
                blockname="Oracle Cloud Infrastructure",
                asn=[],
                expiry="",
                ranges={},
                url="https://docs.oracle.com/en-us/iaas/tools/public_ip_ranges.json",
                src="Oracle ranges",
                search=[],
            ),
        ),
    ],
)
@mock.patch.multiple(
    "asnblock.URLHandler",
    microsoft=mock.DEFAULT,
    google=mock.DEFAULT,
    amazon=mock.DEFAULT,
    icloud=mock.DEFAULT,
    oracle=mock.DEFAULT,
)
def test_provider_getranges(datasource, provider, live_config, **url_handlers):
    ranges = [
        ipaddress.ip_network("185.15.56.0/22"),
        ipaddress.ip_network("2a02:ec80::/29"),
    ]
    targets = (asnblock.Target("enwiki"), asnblock.Target("enwiki", "30"))
    config = live_config._replace(providers=[provider])

    mock_ripestat = mock.Mock()
    if datasource == "ripestat_data":
        data_func = mock_ripestat
    else:
        data_func = url_handlers[datasource]

    data_func.return_value = ranges.copy()

    mock_combine = mock.Mock(side_effect=lambda x: x)
    mock_filter = mock.Mock(side_effect=mock_filter_ranges)

    with mock.patch.multiple(
        "asnblock",
        combine_ranges=mock_combine,
        filter_ranges=mock_filter,
        ripestat_data=mock_ripestat,
    ):
        actual = provider.get_ranges(config, targets)

    assert actual.get(targets[0], []) == ranges
    mock_combine.assert_called_once()
    mock_filter.assert_called_once_with(targets, ranges, provider, config)
    for ds, handler in url_handlers.items():
        if ds != datasource:
            handler.assert_not_called()
    if datasource != "ripestat_data":
        mock_ripestat.assert_not_called()

    data_func.assert_called_once()


@pytest.mark.parametrize(
    "provider",
    [
        asnblock.Provider(
            name="Example",
            blockname="Example",
            asn=[],
            expiry="",
            ranges={},
            url="http://example.com",
            src="Example ranges",
            search=[],
        ),
        asnblock.Provider(
            name="Broken",
            blockname="Broken",
            asn=[],
            expiry="",
            ranges={},
            url="",
            src="",
            search=[],
        ),
    ],
)
@mock.patch.multiple(
    "asnblock.URLHandler",
    microsoft=mock.DEFAULT,
    google=mock.DEFAULT,
    amazon=mock.DEFAULT,
    icloud=mock.DEFAULT,
    oracle=mock.DEFAULT,
)
def test_provider_getranges_error(provider, live_config, **url_handlers):
    targets = (asnblock.Target("enwiki"), asnblock.Target("enwiki", "30"))
    config = live_config._replace(providers=[provider])

    ranges = []

    mock_ripestat = mock.Mock()
    mock_combine = mock.Mock(side_effect=lambda x: x)
    mock_filter = mock.Mock(side_effect=mock_filter_ranges)

    with mock.patch.multiple(
        "asnblock",
        combine_ranges=mock_combine,
        filter_ranges=mock_filter,
        ripestat_data=mock_ripestat,
    ):
        actual = provider.get_ranges(config, targets)

    assert actual.get(targets[0], []) == ranges
    # mock_combine.assert_not_called()
    # mock_filter.assert_not_called()
    for handler in url_handlers.values():
        handler.assert_not_called()
    mock_ripestat.assert_not_called()


def test_collect_data(live_config):
    providers = []
    for provider in live_config.providers[:30]:
        mock_prov = mock.create_autospec(provider)
        mock_prov.name = provider.name
        mock_prov.get_ranges.return_value = getattr(mock.sentinel, provider.name)
        providers.append(mock_prov)

    targets = (asnblock.Target("enwiki"), asnblock.Target("enwiki", "30"))
    config = live_config._replace(providers=providers)
    result = asnblock.collect_data(config, targets)

    for provider in result:
        provider.get_ranges.assert_called_once_with(config, targets)
        assert provider.ranges is getattr(mock.sentinel, provider.name)


@pytest.mark.skip("Not implemented")
def test_provider_dict():
    pass


@pytest.mark.skip("Not implemented")
def test_main():
    pass
