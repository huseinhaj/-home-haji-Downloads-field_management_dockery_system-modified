#!/usr/bin/env python3
"""Chambua OSM health facilities: aina, ukamilifu, mikoa/wilaya."""
import json
from collections import Counter

g = json.load(open('/tmp/health_data/hotosm_tza_health_facilities_points_geojson.geojson', encoding='utf-8'))
feats = g['features']
print('Total features:', len(feats))

amenity = Counter()
healthcare = Counter()
optype = Counter()
addr_city = Counter()
with_name = 0
with_region = 0
for f in feats:
    p = f['properties']
    amenity[p.get('amenity')] += 1
    healthcare[p.get('healthcare')] += 1
    optype[p.get('operator:type')] += 1
    if p.get('name'):
        with_name += 1
    if p.get('addr:city'):
        addr_city[p['addr:city']] += 1
    # kama kuna fields za admin
    for k in p:
        if 'region' in k.lower() or 'district' in k.lower() or 'admin' in k.lower() or 'county' in k.lower():
            with_region += 1

print('\namenity distribution:', dict(amenity.most_common()))
print('\nhealthcare distribution:', dict(healthcare.most_common()))
print('\noperator:type:', dict(optype.most_common()))
print('with name:', with_name)
print('with region/district/admin field:', with_region)
print('\nSample addr:city:', dict(addr_city.most_common(10)))

# OSM points hazina geometry? check
print('\nhas geometry:', bool(feats[0].get('geometry')))

# What about the Readme
print('\n--- Readme.txt ---')
print(open('/tmp/health_data/Readme.txt', encoding='utf-8').read()[:800])
