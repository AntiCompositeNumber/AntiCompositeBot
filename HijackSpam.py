#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: Apache-2.0


# Copyright 2019 AntiCompositeNumber

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generates reports for a link cleanup project"""

import time
import urllib.parse
import json
import requests
import pywikibot
from pywikibot import pagegenerators

version = '1.2.2'


def get_sitematrix():
    """Request the sitematrix from the API, check if open, then yeild URLs"""

    def check_status(checksite):
        """Return true only if wiki is public and open"""
        return ((checksite.get('closed') is None)
                and (checksite.get('private') is None)
                and (checksite.get('fishbowl') is None))

    # Construct the request to the Extension:Sitematrix api
    payload = {"action": "sitematrix", "format": "json",
               "smlangprop": "site", "smsiteprop": "url"}
    headers = {'user-agent': 'HijackSpam ' + version + ' as AntiCompositeBot'
               + ' on Toolforge. User:AntiCompositeNumber, pywikibot/'
               + pywikibot.__version__}
    url = 'https://meta.wikimedia.org/w/api.php'

    # Send the request, except on HTTP errors, and try to decode the json
    r = requests.get(url, headers=headers, params=payload)
    r.raise_for_status()
    result = r.json()['sitematrix']

    # Parse the result into a generator of urls of public open wikis
    for key, lang in result.items():
        if key == 'count':
            continue
        elif key == 'specials':
            for site in lang:
                if check_status(site):
                    yield site['url']
        else:
            for site in lang['site']:
                if check_status(site):
                    yield site['url']


def list_pages(site, target):
    """Takes a site object and yields the pages linking to the target"""

    # Linksearch is specific, and treats http/https and TLD/subdomain
    # links differently, so we need to run through them all
    for num in range(0, 4):
        if num % 2 == 0:
            protocol = 'http'
        else:
            protocol = 'https'

        if num > 1:
            ctar = '*.' + target
        else:
            ctar = target

        for page in pagegenerators.LinksearchPageGenerator(
                ctar, site=site, protocol=protocol):
            yield page


def site_report(pages, site, preload_sums, report_site):
    """Generate the full linksearch report for a site"""

    summary = urllib.parse.quote(preload_sums.get(
        site.code, preload_sums.get('en')))
    wt = ''
    count = 0
    for page in pages:
        count += 1

        wt += ('<li><a href="{url}">{title}</a> '
               '(<a href="{url}?action=edit&summary={summary}&minor=1">'
               'edit</a>)</li>\n').format(
                   title=page.title(), url=page.full_url(), summary=summary)
    if count > 0:
        wt = ('<div class="container">'
              '\n<h3 id="{dbname}">{dbname}: {count}</h3>\n<ul>\n').format(
            dbname=site.dbName(), count=count) + wt + '</ul>\n</div>\n'

    return wt, count


def summary_table(counts):
    """Takes a dictionary of dbnames and counts and returns at table"""

    tot = 0
    total_wikis = 0
    wt = ('\n<div class="container">\n<h2 id="Summary">Summary</h2>'
          '\n<table class="table table-striped table-sm table-bordered">'
          '\n<tr><th>Wiki</th><th>Count</th></tr>')

    for wiki, count in sorted(counts.items()):
        if count > 0:
            wt += ('\n<tr><td><a href="#{wiki}">{wiki}</a></td>\n'
                   '<td>{count}</td></tr>').format(wiki=wiki, count=count)
            tot += count
            total_wikis += 1

    wt += ('\n</table>\n<p>Total wikis: {total_wikis}</p>\n'
           '<p>Total pages: {tot}</p>\n</div>\n').format(
            total_wikis=total_wikis, tot=tot)

    return wt


def run_check(site, runOverride):
    runpage = pywikibot.Page(site, 'User:AntiCompositeBot/HijackSpam/Run')
    run = runpage.text.endswith('True')
    if run is False and runOverride is False:
        print('Runpage is false, quitting...')
        raise pywikibot.UserBlocked


def save_page(new_text):
    with open('/data/project/anticompositebot/www/static/HijackSpam.html',
              'w') as f:
        f.write(new_text)


def main():
    target = 'blackwell-synergy.com'
    counts = {}

    # Set up on enwiki, check runpage, and prepare empty report page
    enwiki = pywikibot.Site('en', 'wikipedia')
    run_check(enwiki, False)
    report_text = '\n\n<h2 class="container">Reports</h2>\n'

    # Load preload summaries from on-wiki json
    config = pywikibot.Page(
        enwiki, 'User:AntiCompositeBot/HijackSpam/config.json')
    preload_sums = json.loads(config.text)

    # Get the list of sites from get_sitematrix(), retrying once
    try:
        sitematrix = get_sitematrix()
    except requests.exceptions:
        time.sleep(5)
        sitematrix = get_sitematrix()

    header = """<!DOCTYPE html>
<html lang="en">
  <head>
    <!-- Required meta tags -->
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">

    <!-- Bootstrap CSS -->
    <link rel="stylesheet" href="https://tools-static.wmflabs.org/cdnjs/ajax/libs/twitter-bootstrap/4.3.1/css/bootstrap.min.css" crossorigin="anonymous">

    <title>HijackSpam</title>
  </head>
  <body>
"""

    footer = """
    <script src="https://tools-static.wmflabs.org/cdnjs/ajax/libs/jquery/3.4.1/jquery.slim.min.js" crossorigin="anonymous"></script>
    <script src="https://tools-static.wmflabs.org/cdnjs/ajax/libs/popper.js/1.15.0/umd/popper.min.js" crossorigin="anonymous"></script>
    <script src="https://tools-static.wmflabs.org/cdnjs/ajax/libs/twitter-bootstrap/4.3.1/js/bootstrap.min.js" integrity="sha384-JjSmVgyd0p3pXB1rRibZUAYoIIy6OrQ6VrjIEaFf/nJGzIxFDsf4x0xIM+B07jRM" crossorigin="anonymous"></script>
  </body>
</html>"""

    # Add the start time to the output
    lead_text = (header + '<div class="container">\n'
                 '<h1>HijackSpam</h1>\n<p>Scanning all public wikis for ' +
                 target + ' at ' + time.asctime() + '.</p>\n</div>\n')

    # Run through the sitematrix. If pywikibot works on that site, generate
    # a report. Otherwise, add it to the skipped list.
    skipped = ''
    for url in sitematrix:
        try:
            cur_site = pywikibot.Site(url=url + '/wiki/MediaWiki:Delete/en')
        except Exception:
            skipped += '<li>{url}</li>\n'.format(url=url)
            continue

        pages = list_pages(cur_site, target)

        report = site_report(pages, cur_site, preload_sums, enwiki)
        report_text += report[0]
        counts[cur_site.dbName()] = report[1]

    report_text += ('\n<div class="container">\n'
                    '<h3 id="Skipped">Skipped</h3>\n<ul>\n' + skipped +
                    '</ul>\n</div>\n')

    # Generate a summary table and stick it at the top
    report_text = lead_text + summary_table(counts) + report_text + footer

    # Save the report
    save_page(report_text)


if __name__ == '__main__':
    main()
