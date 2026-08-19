"""results_analytics.py — Rule-based subject performance stats + recommendations.

Deterministic and dependency-free: given per-student rows (name, score,
grade, optional gender), it produces distribution stats and short,
actionable Swahili recommendations a teacher or academic officer can act
on immediately. No AI/external calls — this stays fast and reproducible
for every PDF/page render.
"""

from __future__ import annotations

from collections import Counter

from ..utils import is_passing_grade

GRADE_ORDER = ['A', 'B+', 'B', 'C+', 'C', 'D', 'E', 'S', 'F']


def compute_subject_stats(rows: list[dict]) -> dict:
    """rows: [{'name', 'score', 'grade', 'gender' (optional 'M'/'F')}, ...]"""
    total = len(rows)
    grade_counts = Counter(r['grade'] for r in rows)
    pass_count = sum(1 for r in rows if is_passing_grade(r['grade']))
    pass_rate = round(pass_count / total * 100, 1) if total else 0.0
    class_avg = round(sum(r['score'] for r in rows) / total, 1) if total else 0.0

    gender_stats = {}
    for g in ('M', 'F'):
        g_rows = [r for r in rows if r.get('gender') == g]
        if g_rows:
            g_pass = sum(1 for r in g_rows if is_passing_grade(r['grade']))
            gender_stats[g] = {
                'count': len(g_rows),
                'pass_rate': round(g_pass / len(g_rows) * 100, 1),
                'avg': round(sum(r['score'] for r in g_rows) / len(g_rows), 1),
            }

    ranked = sorted(rows, key=lambda r: r['score'])
    weakest = ranked[:5]
    strongest = list(reversed(ranked[-3:])) if len(ranked) >= 3 else list(reversed(ranked))

    present_grades = [g for g in GRADE_ORDER if grade_counts.get(g)]

    return {
        'total': total,
        'grade_counts': grade_counts,
        'present_grades': present_grades,
        'pass_count': pass_count,
        'pass_rate': pass_rate,
        'class_avg': class_avg,
        'gender_stats': gender_stats,
        'weakest': weakest,
        'strongest': strongest,
    }


def generate_recommendations(stats: dict, subject_name: str = 'somo hili', lang: str = 'sw') -> list[str]:
    """Rule-based, deterministic recommendations for the teacher, in Swahili or English."""
    total = stats['total']
    if total == 0:
        return ["Hakuna alama za kutosha kutoa mapendekezo."] if lang == 'sw' else ["Not enough scores to generate recommendations."]

    recs: list[str] = []
    pass_rate = stats['pass_rate']
    gc = stats['grade_counts']
    fail_pct = round(gc.get('F', 0) / total * 100, 1)
    top_pct = round((gc.get('A', 0) + gc.get('B', 0)) / total * 100, 1)

    if lang == 'sw':
        if pass_rate >= 80:
            recs.append(
                f"Ufaulu ni mzuri sana ({pass_rate}%). Endelea na mbinu za sasa za ufundishaji wa {subject_name}, "
                "na wape changamoto za ziada wanafunzi wa Daraja A/B ili wasikwame."
            )
        elif pass_rate >= 60:
            recs.append(
                f"Ufaulu uko wastani ({pass_rate}%). Fanya marudio ya haraka kwa dhana zilizoonekana ngumu kabla "
                "ya mtihani unaofuata, hasa kwa wanafunzi wa Daraja C na D."
            )
        elif pass_rate >= 40:
            recs.append(
                f"Ufaulu uko chini ya wastani ({pass_rate}%). Inashauriwa kufanya vipindi vya ziada (remedial) na "
                f"kupitia upya mbinu za ufundishaji wa {subject_name}."
            )
        else:
            recs.append(
                f"Ufaulu ni hafifu sana ({pass_rate}%). Hii inaashiria pengo kubwa la kimsingi — shauriana na Afisa "
                "Taaluma kuhusu mpango maalum wa kunusuru darasa, ikiwemo kufundisha upya dhana za msingi kabla ya "
                "kuendelea na mtaala."
            )

        if fail_pct >= 30:
            recs.append(
                f"Wanafunzi {fail_pct}% wamepata Daraja F. Wapange kwenye vikundi vidogo vya msaada maalum na "
                "wafuatilie maendeleo yao kila wiki."
            )

        if pass_rate >= 40 and top_pct < 15:
            recs.append(
                "Wanafunzi wachache sana wako Daraja A/B — fikiria mazoezi yenye changamoto zaidi ili kuinua "
                "kiwango cha juu cha darasa."
            )

        gender_stats = stats.get('gender_stats') or {}
        if 'M' in gender_stats and 'F' in gender_stats:
            gap = round(gender_stats['M']['pass_rate'] - gender_stats['F']['pass_rate'], 1)
            if abs(gap) >= 15:
                weaker, stronger = ('Wasichana', 'Wavulana') if gap > 0 else ('Wavulana', 'Wasichana')
                recs.append(
                    f"Kuna tofauti kubwa ya ufaulu kati ya jinsia (pointi {abs(gap)}%) — {weaker} wanafanya vibaya "
                    f"zaidi kuliko {stronger}. Chunguza sababu (mahudhurio, ushiriki darasani) na weka mkakati wa "
                    "kuwasaidia."
                )

        weakest = stats.get('weakest') or []
        if weakest and stats['pass_rate'] < 100:
            names = ', '.join(r['name'] for r in weakest if not is_passing_grade(r['grade']) or r['score'] < 45)
            if names:
                recs.append(f"Wanafunzi wa kufuatiliwa kwa karibu (alama za chini kabisa): {names}.")

    else:  # English
        if pass_rate >= 80:
            recs.append(
                f"Pass rate is very good ({pass_rate}%). Keep your current teaching approach for {subject_name}, "
                "and give A/B-grade students extra stretch material so they stay challenged."
            )
        elif pass_rate >= 60:
            recs.append(
                f"Pass rate is moderate ({pass_rate}%). Do a quick revision of the concepts students found hard "
                "before the next exam, especially for C and D-grade students."
            )
        elif pass_rate >= 40:
            recs.append(
                f"Pass rate is below average ({pass_rate}%). Consider extra remedial sessions and revisiting your "
                f"teaching approach for {subject_name}."
            )
        else:
            recs.append(
                f"Pass rate is very weak ({pass_rate}%). This points to a significant foundational gap — discuss "
                "an intervention plan with the academic officer, including re-teaching core concepts before "
                "moving on with the syllabus."
            )

        if fail_pct >= 30:
            recs.append(
                f"{fail_pct}% of students got an F. Group them into small dedicated support sessions and track "
                "their progress weekly."
            )

        if pass_rate >= 40 and top_pct < 15:
            recs.append(
                "Very few students are at Grade A/B — consider higher-order questions to raise the top end of "
                "the class."
            )

        gender_stats = stats.get('gender_stats') or {}
        if 'M' in gender_stats and 'F' in gender_stats:
            gap = round(gender_stats['M']['pass_rate'] - gender_stats['F']['pass_rate'], 1)
            if abs(gap) >= 15:
                weaker, stronger = ('Girls', 'Boys') if gap > 0 else ('Boys', 'Girls')
                recs.append(
                    f"There's a large gender gap in pass rate ({abs(gap)} points) — {weaker} are performing worse "
                    f"than {stronger}. Investigate why (attendance, classroom participation) and set a support plan."
                )

        weakest = stats.get('weakest') or []
        if weakest and stats['pass_rate'] < 100:
            names = ', '.join(r['name'] for r in weakest if not is_passing_grade(r['grade']) or r['score'] < 45)
            if names:
                recs.append(f"Students to follow up with closely (lowest scores): {names}.")

    return recs
