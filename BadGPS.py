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

import requests
import time
import platform
import json
import mwparserfromhell
import pywikibot

version = 'BadGPS 0.1.2'
site = pywikibot.Site('commons', 'commons')


def data_from_petscan(psid, total):
    params = {'format': 'json', 'output_compatibility': 'catscan',
              'sparse': 'on', 'psid': psid, 'output_limit': total}
    headers = {'user-agent': (
        'AntiCompositeBot {version} on Toolforge, '
        '(commons:User:AntiCompositeNumber) '
        'Requests/{requests_version} Python/{python_version}').format(
            version=version, requests_version=requests.__version__,
            python_version=platform.python_version())}
    r = requests.get('https://petscan.wmflabs.org/',
                     params=params, headers=headers)
    r.raise_for_status()
    files = r.json()['*'][0]['a']['*']
    return files


def add_template(page, template):
    wikitext = mwparserfromhell.parse(page.text)
    s = wikitext.get_sections()
    wikitext.insert_after(s[1].strip(),
                          '\n{{{{{template}}}}}'.format(template=template))
    return str(wikitext)


def time_check(start_time, min_wait):
    end_time = time.time()
    diff = end_time - start_time
    if diff < min_wait:
        print('Sleeping...')
        time.sleep(min_wait - diff)
        return
    else:
        return


def save_page(page, summary):
    try:
        page.save(summary=summary, botflag=True)
    except pywikibot.exception.PageNotSaved:
        print('Save failed, trying again soon')
        time.sleep(15)
        page.save(summary=summary, botflag=True)


def run_check(site):
    runpage = pywikibot.Page(site, 'User:AntiCompositeBot/ShouldBeSVG/Run')
    run = runpage.text.endswith('True')
    if not run:
        print('Runpage is false, quitting...')
        raise pywikibot.UserBlocked('Runpage is false')


def double_check(template, page):
    gen = page.itertemplates()
    res = any(map(
        lambda page_template:
        page_template.title() == 'Template:{template}'.format(
            template=template), gen))
    return not res


def main():
    with open('BadGPS.json', 'r') as f:
        config = json.load(f)
    psid = config.get('psid')
    template = config.get('template')
    block_size = config.get('block_size')
    blocks = config.get('blocks')
    seconds_between_edits = config.get('seconds_between_edits')

    for i in range(blocks):
        run_check(site)
        files = data_from_petscan(psid, block_size)
        for filename in files:
            start_time = time.time()
            page = pywikibot.Page(site, filename)

            if double_check(template, page):
                page.text = add_template(page, template)

                time_check(start_time, seconds_between_edits)
                summary = ('Adding {{{{{template}}}}} to files '
                           'in [[petscan:{psid}]] per author request, '
                           'see user page for details (#{version})').format(
                                template=template, psid=psid, version=version)
                save_page(page, summary)
            else:
                continue


if __name__ == '__main__':
    main()
