#!/bin/bash
toolforge-jobs run uncat-cron --command data/project/anticompositebot/AntiCompositeBot/venv/bin/python3 /data/project/anticompositebot/AntiCompositeBot/src/uncat.py --image tf-python-37 --schedule "30 7 */7 * *"
