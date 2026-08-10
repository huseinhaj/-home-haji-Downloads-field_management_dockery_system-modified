#!/bin/bash
cd /tmp/health_data

echo '=== HFR home links ==='
curl -s --max-time 25 'https://hfrportal.moh.go.tz/' -o hfr_home.html
wc -c hfr_home.html
grep -oE 'r=[A-Za-z%2F_]+' hfr_home.html | sort -u | head -30
echo '--- iframe/redirect ---'
grep -oiE '<iframe[^>]*>' hfr_home.html | head -3
grep -oiE 'window\.location[^;]*' hfr_home.html | head -3

echo
echo '=== Try public facility list pages ==='
for r in 'portal%2Ffacilities' 'portal%2Fsearch' 'facility%2Findex' 'portal%2Ffacilitylist' 'site%2Findex'; do
  code=$(curl -s --max-time 20 -o /dev/null -w '%{http_code}' "https://hfrportal.moh.go.tz/web/index.php?r=$r")
  echo "r=$r -> $code"
done

echo
echo '=== HDX package search: tanzania health facilities ==='
curl -s --max-time 30 'https://data.humdata.org/api/3/action/package_search?q=tanzania%20health%20facility&rows=15' \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
for res in d.get('result',{}).get('results',[]):
    print('-', res.get('title'), '|', res.get('name'))
    for r in res.get('resources',[])[:3]:
        print('    ', r.get('format'), r.get('name','')[:60], '|', r.get('url','')[:120])
" 2>&1 | head -50
