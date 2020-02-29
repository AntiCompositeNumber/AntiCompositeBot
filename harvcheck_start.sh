#!/bin/bash
if [ "$1" == "continuous" ]; then
    /data/project/anticompositebot/AntiCompositeBot/venv/bin/python3 /data/project/anticompositebot/AntiCompositeBot/src/harvcheck.py --auto --run
elif [ "$1" == "job" ]; then
    /data/project/anticompositebot/AntiCompositeBot/venv/bin/python3 /data/project/anticompositebot/AntiCompositeBot/src/harvcheck.py --auto --limit --run
fi
