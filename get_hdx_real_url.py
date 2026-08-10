#!/usr/bin/env python3
"""Pata real download URL za tanzania-healthsites kupitia CKAN API."""
import json
import subprocess
import urllib.request

PKG = 'tanzania-healthsites'

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()

# package_show
pkg = json.loads(get(f'https://data.humdata.org/api/3/action/package_show?id={PKG}'))
print('package:', pkg.get('result', {}).get('title'))
for res in pkg.get('result', {}).get('resources', []):
    print('-', res.get('format'), '|', res.get('name'), '|', res.get('url'))

# resource_show for the CSV to get real url
for res in pkg.get('result', {}).get('resources', []):
    if res.get('format') in ('CSV', 'GeoJSON'):
        rid = res['id']
        try:
            info = json.loads(get(f'https://data.humdata.org/api/3/action/resource_show?id={rid}'))
            real = info['result'].get('url')
            print('\nREAL URL for', res.get('format'), ':', real)
            # download
            out = f'/tmp/health_data/tz_healthsites_{res.get("format").lower()}.{"csv" if res.get("format")=="CSV" else "geojson"}'
            subprocess.run(['curl', '-sL', '--max-time', '120', '-A', 'Mozilla/5.0', real, '-o', out], check=True)
            print('downloaded ->', out)
        except Exception as e:
            print('resource_show err:', res.get('format'), e)
