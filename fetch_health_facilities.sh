#!/bin/bash
# Pakua na kuchunguza data za vituo vya afya
set -e
cd /home/haji/Downloads/field_management_dockery_system-modifiedied
mkdir -p /tmp/health_data
cd /tmp/health_data

echo '=== Download HDX OSM health facilities (GeoJSON) ==='
curl -sL --max-time 60 -o osm_health_geojson.zip 'https://s3.dualstack.us-east-1.amazonaws.com/production-raw-data-api/ISO3/TZA/health_facilities/points/hotosm_tza_health_facilities_points_geojson.zip'
ls -la osm_health_geojson.zip
unzip -o -q osm_health_geojson.zip 2>/dev/null || unzip -o osm_health_geojson.zip
ls -la

echo
echo '=== Inspect schema ==='
python3 - <<'EOF'
import json, glob
files = glob.glob('/tmp/health_data/*.geojson')
print('geojson files:', files)
if not files:
    raise SystemExit('no geojson found')
g = json.load(open(files[0], encoding='utf-8'))
print('type:', g.get('type'), '| features:', len(g.get('features', [])))
props = g['features'][0]['properties']
print('sample properties keys:', sorted(props.keys()))
print('sample:', json.dumps(props, ensure_ascii=False)[:400])
EOF

echo
echo '=== hfrportal explore ==='
curl -s --max-time 25 'https://hfrportal.moh.go.tz/' -o /tmp/health_data/hfr_home.html
grep -oiE '(href="[^"]*download[^"]*"|href="[^"]*facility[^"]*"|href="[^"]*excel[^"]*"|href="[^"]*csv[^"]*")' /tmp/health_data/hfr_home.html | sort -u | head -20
echo '--- title ---'
grep -oiE '<title>[^<]*</title>' /tmp/health_data/hfr_home.html | head -2
