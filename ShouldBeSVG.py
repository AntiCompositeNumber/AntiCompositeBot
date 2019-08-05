#!/usr/bin/env python
# coding: utf-8

# ## Generate a dictionary with diagrams that should be SVG.

# In[1]:


import pywikibot
from pywikibot import pagegenerators
import IPython

site = pywikibot.Site('commons', 'commons')
cat = pywikibot.Category(site, 'Category:Diagram images that should use vector graphics')
gen = pagegenerators.CategorizedPageGenerator(cat,recurse=1,namespaces=6)

usageCounts = {}

for page in gen:
    mimetype = pywikibot.FilePage(page).latest_file_info.mime
    if mimetype != 'image/svg+xml':
        try:
            usage = pywikibot.FilePage.globalusage(page)
            l = len(list(usage))
            usageCounts[page] = l
        except pywikibot.NoUsername:
            print('Skipping', page)


# list(usageCounts)

# In[2]:


usageCountsSorted = sorted(usageCounts, key=usageCounts.__getitem__, reverse=True)


# In[3]:


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
        out = f'{i}. [{title}]({url}) ({count})'
        IPython.display.display_markdown(out, raw=True)
        gallery += f'{title}|{i}. Used {count} times.\n'
gallery += '</gallery>\n[[Category:Images that should use vector graphics]]\n[[Category:Diagram images that should use vector graphics]]'
print(gallery)
        
    


#    Copyright 2019 AntiCompositeNumber
# 
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
# 
#      http://www.apache.org/licenses/LICENSE-2.0
# 
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
# 
