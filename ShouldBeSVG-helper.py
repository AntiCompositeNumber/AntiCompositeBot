#!/usr/bin/env python3
"""Determine which ShouldBeSVG task should be run when called by cron"""
import os
from datetime import datetime

#Grab the current weekday and hour as numbers and concatenate them.
dt = datetime.utcnow()
now = int(dt.strftime('%u%H'))

#Crontab entry: 11 2,10,18 * * * jlocal /data/project/anticompositebot/AntiCompositeBot/ShouldBeSVG-helper.py
#Each key corresponds to a now value when the cronjob could be running.
#Each value corresponds to a key in the reports dict in ShouldBeSVG.py
reports = {102: 'diagram', 110: 'graph', 118: 'math',
           202: 'text', 210: 'sport', 218: 'military_insignia',
           302: 'biology', 310: 'ribbon', 318: 'technology',
           402: 'transport_map', 410: 'wikichart', 418: 'physics',
           502: 'chemistry', 510: 'sign', 518: 'jpg',
           602: 'coat_of_arms', 610: 'locator_map', 618: 'logo',
           702: 'map', 710: 'flag', 718: 'symbol_of_municipalities_in_Japan'}

#Find the report we should be running and send that to the grid.
#If there's no report to run this hour, raise an error.
toolpath = '/data/project/anticompositebot/AntiCompositeBot/'

try:
    report = reports[now]
except KeyError:
    print("Check your timing, there's no report to run this hour.")
    raise
else:
    command = ('jsub -m e -j y -o {toolpath}/logs '
               '{toolpath}/ShouldBeSVG.py {report}').format(report=report,
                                                            toolpath=toolpath)
    os.system(command)
