#!/bin/bash
cd /tmp/health_data

echo '=== menu links (r= routes) ==='
grep -oE 'index\.php\?r=[A-Za-z%2F_]+' hfr_index.html | sort -u | head -30

echo
echo '=== plain hrefs ==='
grep -oE 'href="[^"]+"' hfr_index.html | sort -u | grep -viE '(css|\.js|font|#)' | head -30

echo
echo '=== JS files ==='
grep -oE 'src="[^"]+\.js[^"]*"' hfr_index.html | sort -u | head -15

echo
echo '=== any 'facility' mentions in routes/buttons ==='
grep -oiE '[^>]*facilit[^<]*' hfr_index.html | head -20

echo
echo '=== gridview/facility controller probes ==='
for r in 'facility%2Fsearch' 'facility%2Flist' 'facility%2Findex' 'portal%2Fview' 'facility%2Fview%2F1' 'facility%2Fsearch%2Fquery'; do
  code=$(curl -s --max-time 15 -o /tmp/health_data/probe_$RANDOM.html -w '%{http_code}' "https://hfrportal.moh.go.tz/web/index.php?r=$r")
  echo "r=$r -> $code"
done
