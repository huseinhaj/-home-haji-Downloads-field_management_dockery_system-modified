"""Cleanup ya prod data ya Isingiro (idhini ya user: 2026-09-20).

1. Backup rows zinazoathirika → JSON
2. Futa junk FormStudent rows fs=6786, fs=6787 (zilizoundwa na
   add-student bug ya 2026-09-18 — zote mbili "Privatus Gordian Laurian")
3. Tengeneza Student "Privatus Leonce Laurian" (#217) ambaye hakuwahi
   kupata record kwa sababu ya bug ile ile (kaka wake Gordian #216
   alimekula jina lake).

Transaction moja — inafeli au inapita yote.
"""
import json
import os
import sys
from datetime import datetime

import psycopg2

url = os.environ.get('RESULTS_DATABASE_URL')
if not url:
    for line in open('.env'):
        if line.startswith('RESULTS_DATABASE_URL='):
            url = line.strip().split('=', 1)[1]
            break

JUNK_IDS = [6786, 6787]

conn = psycopg2.connect(url, sslmode='require')
conn.autocommit = False
cur = conn.cursor()

def q(sql, args=None, fetch=True):
    cur.execute(sql, args or ())
    if not fetch:
        return None
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

# ── 1) VERIFY: junk rows zipo na zinaonekana kama tulivyotegemea ──────────
junk = q("SELECT * FROM results_formstudent WHERE id = ANY(%s)", (JUNK_IDS,))
if len(junk) != 2:
    print(f"STOP: matarajio rows 2 za junk, DB ina {len(junk)}. Hakuna kitu kimebadilishwa.")
    conn.rollback()
    sys.exit(1)
for j in junk:
    ok = (j['first_name'].lower() == 'privatus'
          and j['middle_name'].lower() == 'gordian'
          and j['last_name'].lower() == 'laurian'
          and j['form'] == 1 and j['is_active'])
    if not ok:
        print(f"STOP: row {j['id']} haifanani na junk ile — {j}. Hakuna kitu kimebadilishwa.")
        conn.rollback()
        sys.exit(1)

# ── 2) BACKUP: kila kitu kinachoathirika → JSON ───────────────────────────
backup = {
    'timestamp': datetime.now().isoformat(),
    'junk_formstudent_rows': junk,
    'real_privatus_rows': q("""
        SELECT * FROM results_formstudent
        WHERE school_id = 1 AND lower(first_name) = 'privatus'
          AND (lower(last_name) IN ('laurian', 'protazi'))
        ORDER BY id
    """),
    'students': q("""
        SELECT * FROM results_student
        WHERE lower(first_name) = 'privatus'
          AND lower(last_name) IN ('laurian', 'protazi')
        ORDER BY id
    """),
}
fname = f"backup_isingiro_leonce_cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(fname, 'w') as f:
    json.dump(backup, f, indent=1, default=str)
print(f"BACKUP imehifadhiwa: {fname}")

# ── 3) DELETE junk rows ──────────────────────────────────────────────────
cur.execute("DELETE FROM results_formstudent WHERE id = ANY(%s)", (JUNK_IDS,))
print(f"DELETED: rows {JUNK_IDS} za junk ('Privatus Gordian Laurian' ×2)")

# ── 4) CREATE Student ya Leonce (#217) — idempotent ──────────────────────
existing = q("""
    SELECT id FROM results_student
    WHERE lower(first_name) = 'privatus' AND lower(middle_name) = 'leonce'
      AND lower(last_name) = 'laurian'
""")
if existing:
    print(f"SKIP: Student 'Privatus Leonce Laurian' tayari ipo (id={existing[0]['id']})")
else:
    cur.execute("""
        INSERT INTO results_student (first_name, middle_name, last_name, gender)
        VALUES ('Privatus', 'Leonce', 'Laurian', 'M')
        RETURNING id
    """)
    new_id = cur.fetchone()[0]
    print(f"CREATED: Student 'Privatus Leonce Laurian' (M) id={new_id}")

# ── 5) VERIFY ya mwisho ──────────────────────────────────────────────────
left = q("""
    SELECT id, first_name, middle_name, last_name FROM results_formstudent
    WHERE school_id = 1 AND lower(first_name) = 'privatus' AND lower(last_name) = 'laurian'
      AND is_active ORDER BY id
""")
print(f"\nBAADA YA CLEANUP — roster 'Privatus ... Laurian' (Form 1):")
for r in left:
    print(f"  fs={r['id']}: {r['first_name']} {r['middle_name']} {r['last_name']}")
assert len(left) == 2, "Matarajio: Gordian + Leonce tu — zaidi zimebaki!"

conn.commit()
print("\nOK — cleanup imepita (committed).")
cur.close()
conn.close()
