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

# import pywikibot
import ipaddress
import requests

sys.path.append(os.path.realpath(os.path.dirname(__file__) + "/.."))
import asnblock  # noqa: E402

# import utils  # noqa: E402

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
    return asnblock.get_config()


def test_get_config(live_config):
    assert isinstance(live_config, dict)


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
        provider = [
            asnblock.Provider(**p)
            for p in live_config["providers"]
            if search in p.get("url", "")
        ][0]
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
    assert asnblock.search_whois(net, [search]) is expected


def test_search_whois_exception():
    mock_session = mock.Mock()
    mock_session.get.return_value.raise_for_status.side_effect = (
        requests.exceptions.HTTPError
    )
    with mock.patch("asnblock.session", mock_session):
        assert (
            asnblock.search_whois(ipaddress.ip_network("127.0.0.1/32"), [""]) is False
        )


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


@pytest.mark.skip("Not implemented")
def test_make_section():
    pass


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
