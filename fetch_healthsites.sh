#!/bin/bash
cd /tmp/health_data

echo '=== Tanzania Healthsites CSV ==='
curl -sL --max-time 90 -o tz_healthsites.csv 'https://data.humdata.org/dataset/eac6c9b4-5d0d-48cc-8914-a667c716c4c5/resource/2d3a9a6f-9ba8-49c6-a912-aad079717121/down'
ls -la tz_healthsites.csv
head -3 tz_healthsites.csv | cut -c1-500

echo
echo '=== Tanzania Healthsites GeoJSON ==='
curl -sL --max-time 90 -o tz_healthsites.geojson 'https://data.humdata.org/dataset/eac6c9b4-5d0d-48cc-8914-a667c716c4c5/resource/41c0a3c9-0cac-442f-87e4-3e3ab0110389/down'
ls -la tz_healthsites.geojson

echo
echo '=== HFR portal facilities page ==='
curl -s --max-time 40 -L -c cookies.txt 'https://hfrportal.moh.go.tz/web/index.php?r=portal%2Ffacilities' -o hfr_facilities.html
wc -c hfr_facilities.html
grep -oE '<title>[^<]*</title>' hfr_facilities.html | head -2
echo '--- table headers if any ---'
grep -oE '<th[^>]*>[^<]*</th>' hfr_facilities.html | head -10
echo '--- grid view / pagination hints ---'
grep -oiE '(pagination|gridview|page=[0-9])' hfr_facilities.html | sort | uniq -c | head
