#!/bin/bash
if [ "$1" == "continuous" ]; then
    /data/project/anticompositebot/AntiCompositeBot/venv/bin/python3 /data/project/anticompositebot/AntiCompositeBot/src/harvcheck.py --auto random --run
elif [ "$1" == "job" ]; then
    /data/project/anticompositebot/AntiCompositeBot/venv/bin/python3 /data/project/anticompositebot/AntiCompositeBot/src/harvcheck.py --auto quarry --limit 9 --run
fi
