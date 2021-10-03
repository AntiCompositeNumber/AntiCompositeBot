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
    return list(asnblock.ripestat_data(wmf_provider))


@pytest.mark.parametrize(
    "ip",
    [
        # anycast
        ipaddress.ip_network("198.35.27.0/24"),
        ipaddress.ip_network("185.71.138.0/24"),
        # eqiad
        ipaddress.ip_network("208.80.154.0/23"),
        ipaddress.ip_network("2620:0:861::/48"),
        ipaddress.ip_network("185.15.56.0/24"),  # cloud
        # codfw
        ipaddress.ip_network("208.80.152.0/23"),
        ipaddress.ip_network("185.15.57.0/24"),
        ipaddress.ip_network("2620:0:860::/48"),
        # ulsfo
        ipaddress.ip_network("198.35.26.0/24"),
        ipaddress.ip_network("2620:0:863::/48"),
        # eqsin
        ipaddress.ip_network("103.102.166.0/24"),
        ipaddress.ip_network("2001:df2:e500::/48"),
        # esams
        ipaddress.ip_network("91.198.174.0/24"),
        ipaddress.ip_network("185.15.58.0/23"),
        ipaddress.ip_network("2620:0:862::/48"),
        ipaddress.ip_network("2a02:ec80::/32"),
    ],
)
def test_ripestat_data(ip, wmf_ripestat_ranges):
    # Testing with WMF ranges, current as of 2021-10-02, data from
    # https://phabricator.wikimedia.org/diffusion/OHPU/browse/master/config/sites.yaml
    # https://phabricator.wikimedia.org/diffusion/OHPU/browse/master/templates/includes/customers/64710.policy
    assert ip in wmf_ripestat_ranges


def test_ripestat_data_raise(wmf_provider):
    mock_get = mock.Mock(spec=session.get)
    mock_req = mock_get.return_value
    mock_req.raise_for_status.side_effect = requests.exceptions.HTTPError
    with mock.patch("asnblock.session.get", mock_get):
        assert list(asnblock.ripestat_data(wmf_provider)) == []

    mock_get.assert_called()


@pytest.mark.parametrize(
    "func,search",
    [
        (asnblock.microsoft_data, "microsoft"),
        (asnblock.amazon_data, "amazon"),
        (asnblock.google_data, "google"),
        (asnblock.icloud_data, "icloud"),
        (asnblock.oracle_data, "oracle"),
    ],
)
def test_url_handler_list(func, search):
    assert asnblock.url_handlers[search] == func


@pytest.mark.parametrize(
    # "search,func", [(search, func) for search, func in asnblock.url_handlers.items()]
    "search, func",
    asnblock.url_handlers.items(),
)
def test_provider_api_data(search, func, live_config):
    provider = next(filter(lambda p: search in p.url, live_config.providers))
    data = func(provider)

    once = False
    for prefix in data:
        assert isinstance(prefix, ipaddress.IPv4Network) or isinstance(
            prefix, ipaddress.IPv6Network
        )
        once = True

    assert once is True


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
def test_search_whois(net, expected, search):
    throttle = mock.Mock(spec=utils.Throttle)
    assert asnblock.search_whois(net, [search], throttle=throttle) is expected
    throttle.throttle.assert_called_once()


def test_search_whois_exception():
    mock_session = mock.Mock()
    mock_session.get.return_value.raise_for_status.side_effect = (
        requests.exceptions.HTTPError
    )
    with mock.patch("asnblock.session", mock_session):
        assert (
            asnblock.search_whois(ipaddress.ip_network("127.0.0.1/32"), [""]) is False
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
    with mock.patch("asnblock.search_whois", mock_search):
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
    mock_template = mock.Mock()
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

    assert len(expiries) == 4


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


def test_filter_ranges(wmf_provider, live_config):
    targets = (asnblock.Target("enwiki"), asnblock.Target("enwiki", "30"))
    ranges = [
        ipaddress.ip_network("91.198.174.0/24"),
        ipaddress.ip_network("103.102.166.0/24"),
        ipaddress.ip_network("185.15.56.0/22"),
        ipaddress.ip_network("185.71.138.0/24"),
        ipaddress.ip_network("198.35.26.0/23"),
        ipaddress.ip_network("208.80.152.0/22"),
        ipaddress.ip_network("2001:df2:e500::/48"),
        ipaddress.ip_network("2620:0:860::/46"),
        ipaddress.ip_network("2a02:ec80::/32"),
    ]
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
    assert result[targets[0]] == ranges
    assert result[targets[1]] == ranges


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
def test_provider_getranges(datasource, provider, live_config):
    url_handlers = {
        "microsoft": mock.Mock(),
        "google": mock.Mock(),
        "amazon": mock.Mock(),
        "icloud": mock.Mock(),
        "oracle": mock.Mock(),
    }

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
        with mock.patch.dict("asnblock.url_handlers", url_handlers):
            actual = provider.get_ranges(config, targets)

    assert actual.get(targets[0], []) == ranges
    mock_combine.assert_called_once_with(ranges)
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
def test_provider_getranges_error(provider, live_config):
    url_handlers = {
        "microsoft": mock.Mock(),
        "google": mock.Mock(),
        "amazon": mock.Mock(),
        "icloud": mock.Mock(),
        "oracle": mock.Mock(),
    }

    targets = (asnblock.Target("enwiki"), asnblock.Target("enwiki", "30"))
    config = live_config._replace(providers=[provider])

    ranges = []

    mock_ripestat = mock.Mock()
    mock_combine = mock.Mock()
    mock_filter = mock.Mock()

    with mock.patch.multiple(
        "asnblock",
        combine_ranges=mock_combine,
        filter_ranges=mock_filter,
        ripestat_data=mock_ripestat,
    ):
        with mock.patch.dict("asnblock.url_handlers", url_handlers):
            actual = provider.get_ranges(config, targets)

    assert actual.get(targets[0], []) == ranges
    mock_combine.assert_not_called()
    mock_filter.assert_not_called()
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
