#!/bin/bash
#
# Usage: run-old-and-new-screenshots.sh <phantomJScloud key>

set -ex

KEY=$1

# old screenshots
python ~/code/covid-tracking-data/screenshots/backup_to_s3.py --phantomjscloud-key $KEY \
    --temp-dir /Users/julia/screenshots --screenshot-core-urls --dry-run >> ~/old_screenshots_core_json.log 2>&1
python ~/code/covid-tracking-data/screenshots/backup_to_s3.py --phantomjscloud-key $KEY \
    --temp-dir /Users/julia/screenshots --screenshot-ltc-urls --dry-run >> ~/old_screenshots_ltc_json.log 2>&1
python ~/code/covid-tracking-data/screenshots/backup_to_s3.py --phantomjscloud-key $KEY \
    --temp-dir /Users/julia/screenshots --screenshot-crdt-urls --dry-run >> ~/old_screenshots_crdt_json.log 2>&1

# new screenshots
python ~/code/screenshots/run-screenshots.py --phantomjscloud-key $KEY --temp-dir /Users/julia/screenshots \
    --screenshot-core-urls --dry-run >> ~/new_screenshots_core_json.log 2>&1
python ~/code/screenshots/run-screenshots.py --phantomjscloud-key $KEY --temp-dir /Users/julia/screenshots \
    --screenshot-ltc-urls --dry-run >> ~/new_screenshots_ltc_json.log 2>&1
python ~/code/screenshots/run-screenshots.py --phantomjscloud-key $KEY --temp-dir /Users/julia/screenshots \
    --screenshot-crdt-urls --dry-run >> ~/new_screenshots_crdt_json.log 2>&1

# compare
python compare_logs.py
