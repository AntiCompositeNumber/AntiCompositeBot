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
import requests
import urllib.parse
import acnutils as utils

sys.path.append(os.path.realpath(os.path.dirname(__file__) + "/.."))
import asnblock  # noqa: E402

session = asnblock.session


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
    return asnblock.Config()


def test_get_config(live_config):
    assert live_config.providers
    assert live_config.ignore
    assert live_config.sites


@pytest.fixture(scope="module")
def rir_data():
    return asnblock.RIRData()


@pytest.mark.slow
def test_rir_data(rir_data):
    assert isinstance(rir_data.ipv4[0], asnblock.DataRow)
    assert isinstance(rir_data.ipv6[0], asnblock.DataRow)
    assert isinstance(rir_data.asn[0], asnblock.DataRow)


@pytest.mark.parametrize(
    "ip",
    [
        ipaddress.ip_network("185.15.56.0/22"),
        ipaddress.ip_network("2a02:ec80::/29"),
        ipaddress.ip_network("91.198.174.0/24"),
        ipaddress.ip_network("2620:0:860::/46"),
        ipaddress.ip_network("198.35.26.0/23"),
        ipaddress.ip_network("208.80.152.0/22"),
        pytest.param(
            ipaddress.ip_network("103.102.166.0/24"),
            marks=pytest.mark.xfail(
                reason=(
                    "IP address data in the RIR bulk reports can't be linked "
                    "to an ASN registered at another RIR"
                )
            ),
        ),
        pytest.param(
            ipaddress.ip_network("2001:df2:e500::/48"),
            marks=pytest.mark.xfail(
                reason=(
                    "IP address data in the RIR bulk reports can't be linked "
                    "to an ASN registered at another RIR"
                )
            ),
        ),
    ],
)
@pytest.mark.slow
def test_get_asn_ranges(ip, rir_data):
    # Testing with WMF ranges, current as of 2021-08-17
    # data from https://wikitech.wikimedia.org/wiki/IP_and_AS_allocations
    asn_list = ["AS14907", "43821"]
    assert ip in rir_data.get_asn_ranges(asn_list)


@pytest.mark.parametrize(
    "func,search",
    [
        (asnblock.microsoft_data, ""),
        (asnblock.amazon_data, "amazon"),
        (asnblock.google_data, ""),
        (asnblock.icloud_data, "icloud"),
        (asnblock.oracle_data, "oracle"),
    ],
)
def test_provider_api_data(func, search, live_config):
    if search:
        provider = next(filter(lambda p: search in p.url, live_config.providers))
        data = func(provider)
    else:
        data = func()

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
def test_not_blocked():
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


def test_make_section(live_config):
    provider = asnblock.Provider(
        name="chocolate",
        asn=["AS9876"],
        search=["banana", "coffee"],
        ranges=[
            ipaddress.IPv4Network("10.0.0.0/16"),
            ipaddress.IPv4Network("10.1.0.0/32"),
            ipaddress.IPv6Network("fd00::/19"),
            ipaddress.IPv6Network("fd00:2000::/128"),
        ],
    )

    site_config = live_config.sites["enwiki"]

    mock_subst = mock.Mock(return_value="")
    mock_template = mock.Mock()
    mock_template.return_value.safe_substitute = mock_subst
    with mock.patch("string.Template", mock_template):
        section = asnblock.make_section(provider, site_config)

    assert "chocolate" in section
    assert "banana" in section
    assert "coffee" in section
    assert "AS9876" in section

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


@pytest.mark.skip("Not implemented")
def test_make_mass_section():
    pass


@pytest.mark.skip("Not implemented")
def test_update_page():
    pass


@pytest.mark.skip("Not implemented")
def test_collect_data():
    pass


@pytest.mark.skip("Not implemented")
def test_provider_dict():
    pass


@pytest.mark.skip("Not implemented")
def test_main():
    pass
