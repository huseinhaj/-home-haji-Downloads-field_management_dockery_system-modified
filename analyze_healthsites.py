#!/usr/bin/env python3
"""Chambua tz_healthsites CSV."""
import csv
from collections import Counter

rows = list(csv.DictReader(open('/tmp/health_data/tz_healthsites_csv.csv', encoding='utf-8')))
print('Total rows:', len(rows))
print('Columns:', len(rows[0]))

amenity = Counter()
healthcare = Counter()
optype = Counter()
status = Counter()
name_count = 0
for r in rows:
    amenity[r.get('amenity') or r.get('#meta +health_amenity_type') or ''] += 1
    healthcare[r.get('healthcare') or ''] += 1
    optype[r.get('operator_type') or r.get('#meta +operator_type') or ''] += 1
    status[r.get('#status+operational_status') or ''] += 1
    if r.get('#loc +name') or r.get('name'):
        name_count += 1

print('\namenity dist:', dict(amenity.most_common(12)))
print('\nhealthcare dist:', dict(healthcare.most_common(12)))
print('\noperator_type dist:', dict(optype.most_common(12)))
print('\nstatus dist:', dict(status.most_common(10)))
print('with name:', name_count)

# sample government facilities
gov = [r for r in rows if (r.get('operator_type') or '').lower() in ('public','government','local_authority')]
print('\ngovernment/public marked:', len(gov))
if gov:
    g = gov[0]
    print('gov sample:', json_dump(g))

# check addr_city values
cities = Counter((r.get('addr_city') or '').strip() for r in rows)
print('\ntop addr_city:', cities.most_common(10))
