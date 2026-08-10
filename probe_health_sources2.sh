#!/bin/bash
cd /tmp/health_data

echo '=== What did HDX return? ==='
head -c 400 tz_healthsites.csv
echo
echo '=== HFR 27 bytes ==='
cat hfr_facilities.html
echo
echo '=== HFR with -L redirects ==='
curl -sL --max-time 30 -A 'Mozilla/5.0' 'https://hfrportal.moh.go.tz/web/index.php?r=portal/facilities' -o hfr_fac2.html
wc -c hfr_fac2.html
grep -oE '<title>[^<]*</title>' hfr_fac2.html | head -2

echo
echo '=== DHS API: SPA facilities Tanzania ==='
curl -s --max-time 40 'https://api.dhsprogram.com/rest/dhs/facilities?countryIds=TZ&f=json&perpage=5' \
  | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print('total:', d.get('Data',[])[0:0] or d.get('TotalCount'))
    for f in d.get('Data',[])[:5]:
        print(json.dumps(f, ensure_ascii=False)[:300])
except Exception as e:
    print('parse err:', e)
" 2>&1

echo
echo '=== DHS surveys list (SPA) ==='
curl -s --max-time 30 'https://api.dhsprogram.com/rest/dhs/surveys?countryIds=TZ&f=json&surveyType=SPA&perpage=10' \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
for s in d.get('Data',[]):
    print(s.get('SurveyId'), '|', s.get('SurveyYearLabel'), '|', s.get('SurveyType'))
" 2>&1
