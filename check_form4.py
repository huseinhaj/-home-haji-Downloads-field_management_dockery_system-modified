"""Read-only: Form 4 exams + score coverage (kwa ajili ya NECTA C.A. form)."""
import os
import psycopg2

url = os.environ.get('RESULTS_DATABASE_URL')
if not url:
    for line in open('.env'):
        if line.startswith('RESULTS_DATABASE_URL='):
            url = line.strip().split('=', 1)[1]
            break

conn = psycopg2.connect(url, sslmode='require', options='-c default_transaction_read_only=on')
conn.autocommit = True
cur = conn.cursor()

def q(sql, args=None):
    cur.execute(sql, args or ())
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

exams = q("""
    SELECT e.id, e.name, e.form, e.exam_type, e.year, e.stream,
           (SELECT count(*) FROM results_processedresult pr WHERE pr.exam_id = e.id) n_results,
           (SELECT count(DISTINCT er.subject_id) FROM results_examresult er WHERE er.exam_id = e.id) n_subjects,
           (SELECT count(*) FROM results_examresult er WHERE er.exam_id = e.id) n_marks
    FROM results_exam e WHERE e.school_id = 1 ORDER BY e.form, e.id
""")
print("EXAMS ZOTE ZA ISINGIRO:")
for e in exams:
    print(f"  id={e['id']} Form{e['form']} [{e['exam_type']}] '{e['name']}' year={e['year']} "
          f"results={e['n_results']} subjects={e['n_subjects']} marks={e['n_marks']}")

# Roster ya Form 4
r4 = q("SELECT count(*) n FROM results_formstudent WHERE school_id=1 AND form=4 AND is_active")
print(f"\nForm 4 active roster: {r4[0]['n']}")
cur.close()
conn.close()
