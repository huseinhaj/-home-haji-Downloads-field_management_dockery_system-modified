#!/usr/bin/env python3
"""
Generates a Django fixture of schools missing from the current schools.json fixture.
Sources:
  - data/necta_schools_2025.csv          → secondary schools (NECTA 2025)
  - data/necta_primary_schools_2025.csv  → primary schools (NECTA 2025)
  - data/School_CG_Secondary_2022-2023.csv → secondary school district info
  - field_app/fixtures/schools.json      → existing schools (to avoid duplicates)
  - field_app/fixtures/districts.json    → district pk lookup
  - field_app/fixtures/regions.json      → region info

Output: field_app/fixtures/missing_schools.json
"""

import json
import csv
import re
from collections import defaultdict

BASE = "/home/haji/Downloads/field_management_dockery_system-modifiedied"


def load(path):
    with open(f"{BASE}/{path}", encoding="utf-8") as f:
        if path.endswith(".json"):
            return json.load(f)
        return list(csv.DictReader(f))


def normalize(s):
    return re.sub(r"[^a-z0-9]", "", s.lower().strip())


def short_name(name):
    """Strip common suffixes for fuzzy matching."""
    name = name.upper().strip()
    suffixes = [
        r"\s+SECONDARY\s+SCHOOL$", r"\s+SECONDARY$", r"\s+SEC\.?\s*SCH$",
        r"\s+PRIMARY\s+SCHOOL$", r"\s+PRIMARY$", r"\s+PRI\.?\s*SCH$",
        r"\s+SEMINARY$",
    ]
    for s in suffixes:
        name = re.sub(s, "", name, flags=re.I).strip()
    return normalize(name)


print("Loading data...")
districts_data = load("field_app/fixtures/districts.json")
regions_data = load("field_app/fixtures/regions.json")
fixture_schools = load("field_app/fixtures/schools.json")
cg_data = load("data/School_CG_Secondary_2022-2023.csv")
necta_sec = load("data/necta_schools_2025.csv")
necta_pri = load("data/necta_primary_schools_2025.csv")

# ── District lookups ──────────────────────────────────────────────────────────
reg_map = {r["pk"]: r["fields"]["name"] for r in regions_data}

dist_by_pk = {d["pk"]: d["fields"] for d in districts_data}

# normalized name → pk  (try full name and without DC/MC/CC/TC)
dist_name_lookup = {}
for d in districts_data:
    n = d["fields"]["name"]
    dist_name_lookup[normalize(n)] = d["pk"]
    short = re.sub(r"\s*(dc|mc|cc|tc)$", "", n.lower().strip())
    dist_name_lookup[normalize(short)] = d["pk"]

# ── Existing schools (avoid duplicates) ───────────────────────────────────────
fixture_codes = set()
fixture_names_sec = set()
fixture_names_pri = set()

for s in fixture_schools:
    code = s["fields"].get("school_code", "").strip()
    if code:
        fixture_codes.add(code)
    lvl = s["fields"].get("level", "")
    n = s["fields"].get("name", "")
    if lvl == "Secondary":
        fixture_names_sec.add(normalize(n))
        fixture_names_sec.add(short_name(n))
    elif lvl == "Primary":
        fixture_names_pri.add(normalize(n))
        fixture_names_pri.add(short_name(n))

print(f"  Existing schools in fixture: {len(fixture_schools)}")
print(f"  Secondary name variants indexed: {len(fixture_names_sec)}")
print(f"  Primary name variants indexed:   {len(fixture_names_pri)}")

# ── Secondary: code → district from CG CSV ────────────────────────────────────
code_to_dist = {}
for row in cg_data:
    code = row["Reg#"].strip()
    council = row["COUNCIL"].strip()
    if not code or not council:
        continue
    dpk = dist_name_lookup.get(normalize(council))
    if dpk:
        code_to_dist[code] = dpk

# Build code-prefix → best district fallback
prefix_votes = defaultdict(lambda: defaultdict(int))
for code, dpk in code_to_dist.items():
    m = re.search(r"S\.(\d+)", code)
    if m:
        prefix = int(m.group(1)) // 100
        prefix_votes[prefix][dpk] += 1

prefix_best = {p: max(v, key=v.get) for p, v in prefix_votes.items()}

print(f"  Code→district from CG:    {len(code_to_dist)}")
print(f"  Prefix→district fallback: {len(prefix_best)}")

# ── Primary: PS code → district (via name matching) ──────────────────────────
# Build fixture primary school name → district pk
fixture_pri_name_dist = {}
for s in fixture_schools:
    if s["fields"].get("level") == "Primary":
        n = s["fields"]["name"]
        fixture_pri_name_dist[normalize(n)] = s["fields"]["district"]
        fixture_pri_name_dist[short_name(n)] = s["fields"]["district"]

# For each PS region+district combo, find the most common district pk via name match
ps_combo_dist = defaultdict(lambda: defaultdict(int))
for row in necta_pri:
    m = re.match(r"PS(\d{2})(\d{2})\d+", row["code"])
    if not m:
        continue
    combo = (m.group(1), m.group(2))
    name = row["name"].strip()
    dpk = (fixture_pri_name_dist.get(normalize(name)) or
           fixture_pri_name_dist.get(short_name(name)))
    if dpk:
        ps_combo_dist[combo][dpk] += 1

ps_combo_best = {combo: max(v, key=v.get) for combo, v in ps_combo_dist.items()}
print(f"  PS combo→district matched: {len(ps_combo_best)} / 184 combos")

# ── Generate missing secondary schools ───────────────────────────────────────
new_schools = []
skipped_no_district = []
max_fixture_pk = max(s["pk"] for s in fixture_schools)
next_pk = max_fixture_pk + 1


def already_exists_sec(code, name):
    if code in fixture_codes:
        return True
    n = normalize(name)
    s = short_name(name)
    return n in fixture_names_sec or s in fixture_names_sec


def already_exists_pri(code, name):
    if code in fixture_codes:
        return True
    n = normalize(name)
    s = short_name(name)
    return n in fixture_names_pri or s in fixture_names_pri


print("\nProcessing secondary schools...")
sec_added = 0
sec_skipped = 0

for row in necta_sec:
    code = row["code"].strip()
    name = row["name"].strip()

    if already_exists_sec(code, name):
        sec_skipped += 1
        continue

    # Get district
    dpk = code_to_dist.get(code)
    if not dpk:
        m = re.search(r"S\.(\d+)", code)
        if m:
            prefix = int(m.group(1)) // 100
            dpk = prefix_best.get(prefix)

    if not dpk:
        skipped_no_district.append({"code": code, "name": name, "level": "Secondary"})
        continue

    new_schools.append({
        "model": "field_app.school",
        "pk": next_pk,
        "fields": {
            "name": name,
            "school_code": code,
            "district": dpk,
            "level": "Secondary",
            "ownership": "government",
            "capacity": 10,
            "current_students": 0,
            "head_name": "",
            "head_phone": "",
            "latitude": None,
            "longitude": None,
            "address": "",
        },
    })
    next_pk += 1
    sec_added += 1

print(f"  Added: {sec_added}  |  Already exist: {sec_skipped}  |  No district: {len(skipped_no_district)}")

# ── Generate missing primary schools ─────────────────────────────────────────
print("Processing primary schools...")
pri_added = 0
pri_skipped = 0

for row in necta_pri:
    code = row["code"].strip()
    name = row["name"].strip()

    if already_exists_pri(code, name):
        pri_skipped += 1
        continue

    m = re.match(r"PS(\d{2})(\d{2})\d+", code)
    dpk = None
    if m:
        combo = (m.group(1), m.group(2))
        dpk = ps_combo_best.get(combo)

    if not dpk:
        skipped_no_district.append({"code": code, "name": name, "level": "Primary"})
        continue

    new_schools.append({
        "model": "field_app.school",
        "pk": next_pk,
        "fields": {
            "name": name,
            "school_code": code,
            "district": dpk,
            "level": "Primary",
            "ownership": "government",
            "capacity": 10,
            "current_students": 0,
            "head_name": "",
            "head_phone": "",
            "latitude": None,
            "longitude": None,
            "address": "",
        },
    })
    next_pk += 1
    pri_added += 1

print(f"  Added: {pri_added}  |  Already exist: {pri_skipped}  |  No district: {len([s for s in skipped_no_district if s['level']=='Primary'])}")

# ── Save fixture ──────────────────────────────────────────────────────────────
out_path = f"{BASE}/field_app/fixtures/missing_schools.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(new_schools, f, ensure_ascii=False, indent=2)

print(f"\n{'='*60}")
print(f"JUMLA ya shule mpya: {len(new_schools)}")
print(f"  Secondary: {sec_added}")
print(f"  Primary:   {pri_added}")
print(f"  Hazikuweza (bila district): {len(skipped_no_district)}")
print(f"Fixture imehifadhiwa: {out_path}")

# ── TUSIIME check ─────────────────────────────────────────────────────────────
tusiime = [s for s in new_schools if "TUSIIME" in s["fields"]["name"].upper()]
print(f"\nTUSIIME: {tusiime}")
if tusiime:
    dpk = tusiime[0]["fields"]["district"]
    d = dist_by_pk[dpk]
    print(f"  → District: {d['name']} ({reg_map[d['region']]})")

# ── Save no-district list for review ─────────────────────────────────────────
if skipped_no_district:
    nd_path = f"{BASE}/data/schools_no_district.csv"
    with open(nd_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["code", "name", "level"])
        writer.writeheader()
        writer.writerows(skipped_no_district)
    print(f"\nShule bila district zimehifadhiwa: {nd_path}")
    print(f"  ({len(skipped_no_district)} shule - zinahitaji wilaya manually)")
