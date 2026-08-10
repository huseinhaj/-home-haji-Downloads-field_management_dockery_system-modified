#!/bin/bash
# Pata URLs za data za vituo vya afya Tanzania

echo '=== 1. open.africa resource (CKAN API) ==='
curl -s --max-time 25 'https://www.open.africa/sq/api/3/action/resource_show?id=f9192849-9b32-4827-90fa-522ec1e84c1e' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('result',{}); print('name:', r.get('name')); print('format:', r.get('format')); print('url:', r.get('url'))" 2>&1

echo
echo '=== 2. open.africa package search: health facilities ==='
curl -s --max-time 25 'https://www.open.africa/sq/api/3/action/package_search?q=health%20facilities&rows=8' \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
for res in d.get('result',{}).get('results',[]):
    print('-', res.get('title'))
    for r in res.get('resources',[]):
        print('   ', r.get('format'), r.get('name'), '|', r.get('url'))
" 2>&1

echo
echo '=== 3. HDX package: hotosm_tza_health_facilities ==='
curl -s --max-time 25 'https://data.humdata.org/api/3/action/package_show?id=hotosm_tza_health_facilities' \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
for r in d.get('result',{}).get('resources',[]):
    print('-', r.get('format'), '|', r.get('name'))
    print('   ', r.get('url'))
" 2>&1 | head -30

echo
echo '=== 4. Tanzania HMIS DHIS2 public API test ==='
curl -s --max-time 20 -o /dev/null -w 'hmis.moh.go.tz status: %{http_code}\n' 'https://data.hmis.moh.go.tz/api/organisationUnits.json?pageSize=1' 2>&1 || echo 'hmis unreachable'

echo
echo '=== 5. HFR portal test ==='
curl -s --max-time 20 -o /dev/null -w 'hfrportal.moh.go.tz status: %{http_code}\n' 'https://hfrportal.moh.go.tz/' 2>&1 || echo 'hfr unreachable'
