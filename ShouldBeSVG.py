#!/usr/bin/env python3
# coding: utf-8
# SPDX-License-Identifier: Apache-2.0


   # Copyright 2019 AntiCompositeNumber 

   # Licensed under the Apache License, Version 2.0 (the "License");
   # you may not use this file except in compliance with the License.
   # You may obtain a copy of the License at

       # http://www.apache.org/licenses/LICENSE-2.0

   # Unless required by applicable law or agreed to in writing, software
   # distributed under the License is distributed on an "AS IS" BASIS,
   # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   # See the License for the specific language governing permissions and
   # limitations under the License.

version = 'ShouldBeSVG 0.2.1'

import pywikibot
from pywikibot import pagegenerators

def getUsage(cat):

    gen = pagegenerators.CategorizedPageGenerator(cat,recurse=1,namespaces=6)


    # Generate a dictionary with diagrams that should be SVG.
    usageCounts = {}

    for page in gen:
        try:
            mimetype = pywikibot.FilePage(page).latest_file_info.mime
        except pywikibot.PageRelatedError:
            print('Skipping', page)
        else:
            if mimetype != 'image/svg+xml':
                try:
                    usage = pywikibot.FilePage.globalusage(page)
                    l = len(list(usage))
                    usageCounts[page] = l
                except (pywikibot.NoUsername, pywikibot.PageRelatedError):
                    print('Skipping', page)


    # Sort from greatest to least
    usageCountsSorted = sorted(usageCounts, key=usageCounts.__getitem__, reverse=True)

    # Count the global usage for the top 200 files
    i = 0
    j = 200
    gallery = 'Total number of scanned files: {}\n'.format(len(list(usageCounts)))
    gallery += '<gallery showfilename=yes >\n'
    for page in usageCountsSorted:
        if i < j:
            i += 1
            url = page.full_url()
            title = page.title()
            count = usageCounts[page]
            gallery += '{title}|{i}. Used {count} times.\n'.format(title=title, i=i, count=count)
    gallery += '</gallery>\n[[Category:Images that should use vector graphics]]\n[[Category:Diagram images that should use vector graphics]]'
    return gallery

def savePage(target, text):
    site = pywikibot.Site('commons', 'commons')
    target.text = text
    target.save(summary='Updating gallery (Bot) ({version})'.format(version=version), botflag=False) 

site = pywikibot.Site('commons', 'commons')
cat = pywikibot.Category(site, 'Category:Diagram images that should use vector graphics')
target = pywikibot.Page(site, 'Top 200 diagram images that should use vector graphics')

galleryWikitext = getUsage(cat)
#savePage(target, galleryWikitext)
print(galleryWikitext)


