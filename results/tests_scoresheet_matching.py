"""Panga mistari ya scoresheet kwa namba ya 'Na.' iliyochapishwa.

Karatasi ya scoresheet inachapishwa na mfumo mwenyewe, kwa hivyo namba
ya 'Na.' kwenye ukurasa ndiyo funguo ya mwanafunzi. AI inapaswa kusoma
TU alama — jina ni KUHIAKIKI. Majaribio haya yanashikilia hivyo, na
pia mazingira ambayo jina limekuwa mwafaka wa mwanagenzaji.
"""
from django.test import SimpleTestCase

from results.services.speech_submission_service import (
    NAME_OVERRIDE_MARGIN,
    match_rows_to_roster_by_position,
)


class _Student:
    """Mwanagenzi wa majaribio — kijengo tu, hakuhitaji database."""

    def __init__(self, pk, first, last, middle=''):
        self.id = pk
        self.first_name = first
        self.middle_name = middle
        self.last_name = last

    @property
    def name(self):
        return ' '.join(p for p in [self.first_name, self.middle_name, self.last_name] if p)

    def __repr__(self):
        return f'<Student {self.id} {self.name}>'


def _roster(*names):
    return [_Student(i + 1, *name.split(' ', 1)) for i, name in enumerate(names)]


def _row(row, name, score=70):
    return {'row': row, 'raw_name': name, 'score': score, 'is_absent': False, 'blank': False}


def _blank_row(row, name):
    return {'row': row, 'raw_name': name, 'score': None, 'is_absent': False, 'blank': True}


def _names_by_row(rows, rosti):
    assignments, _ = match_rows_to_roster_by_position(rows, rosti)
    return {i: student.name for i, (student, _) in assignments.items()}


class RowNumberFirstMatchingTests(SimpleTestCase):
    def setUp(self):
        # Baadhi ya majina haya yanafamilia moja ('John Mushi' /
        # 'Emmanuel Mushi'), ambayo ndiyo inayofanya kina la WRatio
        # kuwa juu kuliko inavyotarajiwa.
        self.rosti = _roster(
            'John Massawe',
            'Peter Mushi',
            'Neema Joseph',
            'Emmanuel John Mushi',
            'Emmanuel Peter Mushi',
        )

    def test_row_number_and_name_agreeing_is_the_normal_case(self):
        """Hali ya kawaida: AI imesoma kila kitu vizuri. Namba na jina
        zinakubaliana, kwa hivyo kila mwanafunzi hupata alama yake."""
        rows = [_row(i + 1, s.name) for i, s in enumerate(self.rosti)]
        self.assertEqual(_names_by_row(rows, self.rosti), {
            i: s.name for i, s in enumerate(self.rosti)
        })

    def test_misread_name_keeps_its_own_row(self):
        """AI imesoma jina la mwanafunzi MWINGINE kwenye mstari wa
        kwamba. Mwanzo hii ilimkosea: jina lilikuwa namba ya kwanza
        kwa ratibu, kwa hivyo alama yalienda kwa mwanafunzi mwingine
        bila kuonekana. Namba ya 'Na.' ndiyo inapaswa kushinda —
        ndiyo mfumo mwenyewe aliyeichapisha."""
        rows = [
            _row(1, 'John Massawe'),
            _row(2, 'Emmanuel John Mushi'),   # mwanafunzi wa 4, kwenye mstari wa 2
            _row(3, 'Neema Joseph'),
            _row(4, 'Emmanuel Peter Mushi'),
            _row(5, 'Peter Mushi'),            # mwanafunzi wa 2, kwenye mstari wa 5
        ]
        self.assertEqual(_names_by_row(rows, self.rosti), {
            0: 'John Massawe',
            1: 'Peter Mushi',                # mstari wa 2 -> mwanafunzi wa 2
            2: 'Neema Joseph',
            3: 'Emmanuel John Mushi',        # mstari wa 4 -> mwanafunzi wa 4
            4: 'Emmanuel Peter Mushi',       # mstari wa 5 -> mwanafunzi wa 5
        })

    def test_twins_do_not_steal_each_others_row(self):
        """Waawili wa jina la mfamilia hufanana kwa kina 0.81 — juu ya
        kizingiti cha jina (0.80). Kama jina tu litakuwa ufunguo,
        mwanafunzi mmoja angechukua alama za mwenzake na yule mwingine
        angebaki bila alama. Jinalofanana karibu na nafasi iliyochapishwa
        ni ushahidi WA DUMU — namba ndiyo inapaswa kushinda."""
        rows = [
            _row(5, 'Emmanuel John Mushi'),    # mstari wa 5 ni Emmanuel PETER
            _row(4, 'Emmanuel Peter Mushi'),   # mstari wa 4 ni Emmanuel JOHN
        ]
        self.assertEqual(_names_by_row(rows, self.rosti), {
            0: 'Emmanuel Peter Mushi',        # alama yake mwenyewe
            1: 'Emmanuel John Mushi',
        })

    def test_name_wins_when_it_is_clearly_better_than_the_slot(self):
        """Lalamiko la 2026-09-23: rosti ya skrini ilibadilika baada ya
        karatasi kuchapishwa, kwa hivyo nafasi za 'Na.' zilikuwa
        zimechukua na wanafunzi wengine. Jina la kwazi linalofanana
        zaidi kuliko jina la nafasi (tofauti kubwa kuliko
        NAME_OVERRIDE_MARGIN) ndilo linaondoa mstari kutoka
        nafasi yake."""
        self.assertGreater(1.0 - 0.60, NAME_OVERRIDE_MARGIN)  # kina halisi hapa chini
        rosti = _roster('Zaina Juma', 'Amina Said', 'Peter Mushi')
        assignments, unresolved = match_rows_to_roster_by_position(
            [_row(1, 'Amina Said')], rosti,   # 'Amina Said' kina 0.60 na nafasi ya 1
        )
        self.assertEqual(unresolved, [])
        self.assertEqual(assignments[0][0].name, 'Amina Said')
        # Jina lilimekuwa ndio ushahidi, si namba — mwalimu anapaswa
        # kuiona mistari ya kahawia (UI inalenga confidence < 0.90),
        # hata jina lilikuwa 1.00.
        self.assertLess(assignments[0][1], 0.90)

    def test_close_call_between_name_and_slot_keeps_the_slot(self):
        """Jina lililosomwa linafanana vizuri na mwanafunzi MWINGINE
        (kina 1.00 dhidi ya 'Ali Juma'), lakini WRatio pia hupewa
        'Zaina Juma' kina 0.78 kwa sababu ya maneno yaliyotumika.
        Tofauti hiyo (0.22) ni ndogo kuliko NAME_OVERRIDE_MARGIN, kwa
        hivyo nafasi ya kuchapishwa ndiyo inashikilia — AI kimesoma
        jina la mwanafunzi mwenzine."""
        rosti = _roster('Zaina Juma', 'Ali Juma', 'Peter Mushi')
        assignments, _ = match_rows_to_roster_by_position(
            [_row(1, 'Ali Juma')], rosti,
        )
        self.assertEqual(assignments[0][0].name, 'Zaina Juma')

    def test_row_without_a_number_falls_back_to_the_name(self):
        """Baadhi ya vituo havisomi namba ya 'Na.' (AI haikuijibu, au
        mstari ulikatika). Hao mistari haipaswi kupoteka — jina ndilo
        lilobaki."""
        rows = [
            {'row': None, 'raw_name': 'John Massawe', 'score': 70,
             'is_absent': False, 'blank': False},
            _row(2, 'Peter Mushi'),
        ]
        self.assertEqual(_names_by_row(rows, self.rosti), {
            0: 'John Massawe',
            1: 'Peter Mushi',
        })

    def test_row_number_outside_the_roster_is_ignored(self):
        """Namba ya 'Na.' 99 kwenye rosti ya wanafunzi 5 ni makosa ya
        AI, si sababu ya kumpa mwanafunzi mtu mwingine zaidi. Mwanafunzi
        wa 3 ameshakiliwa na mstari wa 3 (ambao namba yake ni sahihi),
        kwa hivyo mstari wa 99 hubaki bila mtu — matokeo salama:
        mwalimu anakagua mwenyewe badala ya mtu apate alama ya
        mwingine bila sababu."""
        rows = [_row(99, 'Neema Joseph'), _row(3, 'Neema Joseph')]
        assignments, unresolved = match_rows_to_roster_by_position(rows, self.rosti)
        self.assertEqual(
            {i: student.name for i, (student, _) in assignments.items()},
            {1: 'Neema Joseph'},
        )
        self.assertEqual(unresolved, [0])

    def test_blank_row_still_claims_its_slot(self):
        """Mstari BLANK (cell tupu kwenye karatasi) bado ni mstari wa
        mwanafunzi wake. Kama hawezi kuchukua nafasi yake, mstari
        unaofuata unaweza kuchukua mwanafunzi mtu mmoja mara mbili."""
        rows = [
            _row(1, 'John Massawe'),
            _blank_row(2, 'Peter Mushi'),
            _row(3, 'Neema Joseph'),
        ]
        assignments, unresolved = match_rows_to_roster_by_position(rows, self.rosti)
        self.assertEqual(unresolved, [])
        self.assertEqual(
            {i: student.name for i, (student, _) in assignments.items()},
            {0: 'John Massawe', 1: 'Peter Mushi', 2: 'Neema Joseph'},
        )

    def test_one_student_is_never_claimed_twice(self):
        """AI ikisoma jina la mwanafunzi wa 1 mara mbili (mchapa
        mkali), mwanafunzi wa 1 hapaswi kupata alama mbili. Mstari
        wa pili hauna mtu — ndio anayeachwa kwa mwalimu kuhakiki,
        badala ya kwamba mwanafunzi wa 2 apate alama ya mtu mwingine
        bila sababu."""
        rows = [_row(1, 'John Massawe'), _row(2, 'John Massawe')]
        assignments, _ = match_rows_to_roster_by_position(rows, self.rosti)
        claimed = [student.id for student, _ in assignments.values()]
        self.assertEqual(len(claimed), len(set(claimed)))
        self.assertEqual(assignments[0][0].name, 'John Massawe')
        self.assertNotIn(1, assignments)

    def test_excluded_students_keep_their_slot_but_cannot_be_claimed(self):
        assignments, _ = match_rows_to_roster_by_position(
            [_row(1, 'John Massawe')], self.rosti, exclude_ids=[self.rosti[0].id],
        )
        self.assertEqual(assignments, {})

    def test_name_belonging_to_nobody_in_the_roster_stays_unmatched(self):
        """Jina ambalo halipo kwenye rosti KABISA, na hakuna namba
        inayosaidia — mstari huu haipaswi kupewa mwanafunzi
        mpatikano. Mwanagenzi huona jina lake kwenye orodha ya
        'hakupatikana' na anaweza kujaza mwenyewe."""
        rows = [_row(1, 'Zachary Unknown Student')]
        assignments, unresolved = match_rows_to_roster_by_position(rows, self.rosti)
        self.assertEqual(assignments, {})
        self.assertEqual(unresolved, [0])
