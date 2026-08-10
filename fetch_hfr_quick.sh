#!/bin/bash
cd /tmp/health_data

echo '=== HFR quick-search ALLs ==='
curl -sL --max-time 60 -A 'Mozilla/5.0' 'https://hfrportal.moh.go.tz/web/index.php?r=portal%2Fquick-search&filters=ALLs' -o hfr_quick_all.html
wc -c hfr_quick_all.html

echo '--- title ---'
grep -oE '<title>[^<]*</title>' hfr_quick_all.html | head -1

echo '--- table headers ---'
grep -oE '<th[^>]*>[^<]{0,40}</th>' hfr_quick_all.html | head -12

echo '--- pagination ---'
grep -oE '(page=[0-9]+|Page [0-9]+ of [0-9]+|records[^<]{0,30})' hfr_quick_all.html | sort -u | head -10

echo '--- facility name cells sample ---'
grep -oE '<td[^>]*>[^<]{0,60}</td>' hfr_quick_all.html | head -15

echo '--- total count hint ---'
grep -oiE '[0-9,]+ (facilit|record|facility)' hfr_quick_all.html | head -5
