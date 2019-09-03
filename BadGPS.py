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

import pywikibot
import requests
import mwparserfromhell
import time

version = 'BadGPS 0.1.0'
site = pywikibot.Site('commons', 'commons')


def data_from_petscan(psid, total):
    params = {'format': 'json', 'output_compatibility': 'catscan',
              'sparse': 'on', 'psid': psid, 'output_limit': total}
    headers = {'user-agent': 'AntiCompositeBot BadGPS on PAWS'}
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


def time_check(start_time):
    end_time = time.time()
    diff = end_time - start_time
    min_wait = 5
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
        raise pywikibot.UserBlocked


def main():
    psid = 10891872
    template = 'Location estimated'
    block_size = 5
    blocks = 1

    for i in range(blocks):
        run_check(site)
        files = data_from_petscan(psid, block_size)
        for filename in files:
            start_time = time.time()
            page = pywikibot.Page(site, filename)
            page.text = add_template(page, template)

            time_check(start_time)
            summary = ('Adding {{{{{template}}}}} to files '
                       'in [[petscan:{psid}]] per author request, '
                       'see user page for details (BadGPS)').format(
                            template=template, psid=psid)
            save_page(page, summary)


if __name__ == '__main__':
    main()
