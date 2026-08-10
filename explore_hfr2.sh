#!/bin/bash
cd /tmp/health_data

echo '=== HFR root content (151 bytes) ==='
curl -s --max-time 25 'https://hfrportal.moh.go.tz/' | head -c 500
echo
echo '=== HFR portal/index ==='
curl -sL --max-time 25 'https://hfrportal.moh.go.tz/web/index.php?r=portal/index' -o hfr_index.html
wc -c hfr_index.html
grep -oE '<title>[^<]*</title>' hfr_index.html | head -2

echo
echo '=== search for form/inputs in index ==='
grep -oE '<(form|input|select|button)[^>]*>' hfr_index.html 2>/dev/null | head -20

echo
echo '=== try facilities ajax with POST ==='
curl -s --max-time 25 -X POST 'https://hfrportal.moh.go.tz/web/index.php?r=portal/facilities' \
  -d 'page=1' -H 'X-Requested-With: XMLHttpRequest' -A 'Mozilla/5.0' | head -c 400
echo

echo '=== geoBoundaries TZA ADM2 ==='
curl -s --max-time 30 'https://www.geoboundaries.org/api/current/gbOpen/TZA/ADM2/' \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('boundaryName:', d.get('boundaryName'))
print('downloadURL:', d.get('gjDownloadURL') or d.get('simplifiedGeometryGeoJSON'))
print('linkData:', d.get('linkData'))
" 2>&1
