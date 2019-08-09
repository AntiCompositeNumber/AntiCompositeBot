#!/usr/bin/env python3

import os
from datetime import datetime

#Grab the current weekday and hour as numbers and concatenate them.
dt = datetime.utcnow()
now = int(dt.strftime('%u%H'))

#Each key corresponds to a now value when the cronjob could be running.
#Each value corresponds to a key in the reports dict in ShouldBeSVG.py
reports = {100: 'diagram', 108: 'graph', 116: 'math',
           200: 'text', 208: 'sport', 216: 'military_insignia',
           300: 'biology', 308: 'ribbon', 316: 'technology',
           400: 'transport_map', 408: 'chemical', 416: 'physics',
           500: 'chemistry', 508: 'sign', 516: 'jpg', 
           600: 'coat_of_arms', 608: 'locator_map', 616: 'logo',
           700: 'map', 708: 'flag', 716: 'symbol of municipalities in Japan'}

#Find the report we should be running and send that to the grid.
#If there's no report to run this hour, raise an error.
toolpath = /data/project/anticompositebot/AntiCompositeBot/ShouldBeSVG.py
try:
    report = reports[now]
except KeyError:
    print("Check your timing, there's no report to run this hour.")
    raise
else:
    os.system('jsub -m e {toolpath} {report}'.format(report = report)
