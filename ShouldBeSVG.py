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

"""Generates reports for highly-used images that should use vector graphics."""

import datetime
import argparse
import re
import json
import time
import subprocess
import os
import pywikibot
from pywikibot import pagegenerators

version = 'ShouldBeSVG 1.2.1'
toolforge = None

def check_toolforge():
    """Check if the script is running on the grid"""
    job = os.getenv('JOB_ID')
    if job is not None:
        print('Toolforge grid detected, job number', job)
        return job

    print('Toolforge grid not detected, errors will not be reported')
    return False

def grid_handle_error():
    """If there's an exception, I want to know about it."""
    if bool(toolforge):
        subprocess.run(['qalter', '-m', 'e', '/ShouldBeSVG/'])

def get_usage(cat, depth, total):
    """Get usage information for every file in the supplied category"""
    gen = pagegenerators.CategorizedPageGenerator(cat, recurse=depth,
                                                  namespaces=6, total=total)

    # Generate a dictionary with diagrams that should be SVG.
    usageCounts = {}
    skipped = []

    for page in gen:
        # First, grab the mimetype of the file.
        # If that's not possible, the file is broken and should be skipped.
        try:
            mimetype = pywikibot.FilePage(page).latest_file_info.mime
        except pywikibot.PageRelatedError:
            skipped.append(page.title())
            print('Skipping', page)
        else:
            # The categories are a bit messy, so make sure the image isn't
            # already an SVG.
            if mimetype != 'image/svg+xml':
                try:
                    # Grab the global usage of the file, then count the items
                    # and save them in the dictionary.
                    usage = pywikibot.FilePage.globalusage(page)
                    usageCounts[page] = len(list(usage))
                except (pywikibot.NoUsername, pywikibot.PageRelatedError):
                    # Pywikibot complains if the bot doesn't have an account
                    # on a wiki where a file is used. If that happens,
                    # skip the file.
                    skipped.append(page.title())
                    print('Skipping', page)

    # Sort from greatest to least
    usageCountsSorted = sorted(usageCounts, key=usageCounts.__getitem__,
                               reverse=True)

    # Count the global usage for the top 200 files
    i = 0
    j = 200
    sortedPages = ''
    for page in usageCountsSorted:
        if i < j:
            i += 1
            sortedPages += '{title}|{i}. Used {count} times.\n'.format(
                title=page.title(), i=i, count=usageCounts[page])
    print('Scanning finished')
    return sortedPages, len(usageCounts), skipped

def construct_gallery(cat, usage_result, depth):
    """Take the output from get_usage() and turn it into a wikitext gallery"""
    date = datetime.date.today()
    cats = "'''[[:{maincat}]]''' ({num} files) \n".format(
        maincat=cat.title(), num=cat.categoryinfo['files'])
    pageCats = ('{maincat}\n'
                '[[Category:Images that should use vector graphics]]').format(
                    maincat=cat.aslink())

    # Figure out which subcategories were scanned and turn those into a list
    if depth > 0:
        for subcat in cat.subcategories(recurse=depth - 1):
            cats += "* [[:{subcat}]] ({num} files) \n".format(
                subcat=subcat.title(), num=subcat.categoryinfo['files'])

    # If any files were skipped, write an explanatory message and the files.
    skipped = usage_result[2]
    if skipped != []:
        skippedFiles = ('The following files were skipped due to errors '
                        'during the generation of this report:\n')\
                        .format(skipped=skipped)
        for page in skipped:
            skippedFiles += '* [[:{title}]]\n'.format(title=page.title())
    else:
        skippedFiles = '\n'

    # Now we construct the gallery itself. Everything is formatted by now,
    # it just needs to be slotted into the right spot.
    gallery = """\
Last update: {{{{ISODate|1={date}}}}}.

This report includes the following categories while counting only the usage \
of each file in the main namespace.

{cats}
Total number of scanned files: {totalScanned}
<gallery showfilename=yes>
{sortedPages}
</gallery>

This report was generated by AntiCompositeBot {version}. {skippedFiles}
{pageCats}""".format(date=date, cats=cats, totalScanned=usage_result[1],
                     sortedPages=usage_result[0], skippedFiles=skippedFiles,
                     pageCats=pageCats, version=version)
    return gallery

def save_page(target, gallery):
    """Saves the page to Commons, making sure to leave text above the line"""
    oldWikitext = target.text
    regex = re.compile(
        '(?<=<!-- Only text ABOVE this line '
        'will be preserved on updates -->\n).*', re.M | re.S)
    newWikitext = re.sub(regex, gallery, oldWikitext)
    target.text = newWikitext
    try:
        target.save(summary='Updating gallery (Bot) ({version})'.format(
            version=version), botflag=False)
    except pywikibot.PageNotSaved:
        print('Save failed, trying again soon')
        time.sleep(15)
        try:
            target.save(summary='Updating gallery (Bot) ({version})'.format(
                version=version), botflag=False)
        except pywikibot.PageNotSaved:
            print(target.text)
            raise

def handle_args():
    # Handle command line arguments. See ShouldBeSVG.py --help for details
    parser = argparse.ArgumentParser(
        description='Generate global usage reports for vectorization categories.')
    parser.add_argument('key')
    parser.add_argument('--total', help="maximum number of files to scan",
                        type=int, default=None)
    parser.add_argument('--simulate', action="store_true",
                        help="prints output to SDOUT instead of saving it",)
    parser.add_argument('--run_override', action='store_true',
                        help='force the bot to ignore the runpage')
    parser.add_argument('--version', action='version', version=version)
    return parser.parse_args()

def find_report(args, times):
    if args.key == 'auto':
        dt = datetime.datetime.utcnow()
        now = dt.strftime('%u%H')
        try:
            report = times[now]
        except KeyError:
            print("Check your timing, there's no report to run this hour", now)
            raise
    else:
        report = args.key

    if bool(toolforge):
        subprocess.run(['qalter', '-N',
                        'ShouldBeSVG-{report}'.format(report=report),
                        toolforge])
    return report

def run_check(site, runOverride):
    runpage = pywikibot.Page(site, 'User:AntiCompositeBot/ShouldBeSVG/Run')
    run = runpage.text.endswith('True')
    if run is False and runOverride is False:
        print('Runpage is false, quitting...')
        raise pywikibot.UserBlocked


def main():
    global toolforge
    toolforge = check_toolforge()
    args = handle_args()

    # Set up pywikibot to operate off of Commons
    site = pywikibot.Site('commons', 'commons')

    run_check(site, args.run_override)

    # Log the version and the start time
    print('AntiCompositeBot {version} started at {starttime}'.format(
        version=version, starttime=datetime.datetime.now().isoformat()))


    # Download a dict relating keys to galleries, categories, and depth values.
    reportsPage = pywikibot.Page(
        site, 'User:AntiCompositeBot/ShouldBeSVG/reports.json')
    reports = json.loads(reportsPage.text)['reports']
    times = json.loads(reportsPage.text)['times']

    # Collect information from arguments
    key = find_report(args, times)
    cat = pywikibot.Category(site, reports[key]['category'])
    target = pywikibot.Page(site, reports[key]['gallery'])
    depth = reports[key]['depth']
    total = args.total

    # Run get_usage() with the cat based on the input. Returns the files with
    # their usage, the total number scanned, and any that were skipped.
    usage_result = get_usage(cat, depth, total)

    # Use all the information gathered or supplied to construct the report gallery.
    gallery = construct_gallery(cat, usage_result, depth)

    # Check if we're actually writing to the report gallery. If not, just print
    # the gallery wikitext to SDOUT. If we are, send it to save_page().
    if args.simulate:
        print(gallery)
    else:
        save_page(target, gallery)

    #We're done here.
    print('Finished')

if __name__ == '__main__':
    try:
        main()
    except Exception:
        grid_handle_error()
        raise
