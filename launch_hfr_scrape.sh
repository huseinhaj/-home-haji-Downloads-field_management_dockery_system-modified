#!/bin/bash
cd /home/haji/Downloads/field_management_dockery_system-modifiedied

echo '=== TEST: pages 1-2 ==='
python3 scrape_hfr.py 1 2 2>&1 | tail -4
echo
echo '=== verify CSV ==='
python3 -c "
import csv
rows = list(csv.DictReader(open('/tmp/health_data/hfr_facilities.csv', encoding='utf-8-sig')))
print('rows:', len(rows))
for r in rows[:4]:
    print(' ', r['code'], '|', r['name'], '|', r['type'], '|', r['region'], '|', r['council'], '|', r['ownership_category'], '|', r['ownership_authority'], '|', r['status'])
"
echo
echo '=== LAUNCH FULL SCRAPE (background) ==='
nohup python3 scrape_hfr.py 1 713 > /tmp/health_data/scrape_hfr.log 2>&1 &
echo "PID: $!"
sleep 3
head -3 /tmp/health_data/scrape_hfr.log
