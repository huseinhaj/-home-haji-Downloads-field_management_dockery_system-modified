"""
Joint exams za wilaya (Halmashauri).

Mtiririko:
  1. Afisa Wilaya (TeacherAccount.ROLE_DISTRICT) anaunda JointExam mara moja
     (mf. "Form One Mid Term Joint, Sept 2026") na kuchagua shule zinazoshiriki.
  2. Mfumo unaunda Exam ya kawaida kwa KILA shule (Exam.joint_exam = hii) +
     SubjectSubmission za masomo ambayo shule hiyo inafundisha.
  3. Walimu wa kila shule wanaingiza alama kama kawaida; Mtaaluma anaidhinisha.
  4. Afisa anaona ranking ya shule zote + anapakua Excel ya Halmashauri;
     shule zinaona performance ya wilaya nzima baada ya afisa kuifungua.
"""
import re

from django.db import models


def district_key(name):
    """"Kyerwa", "KYERWA DC", "Kyerwa District Council" → "kyerwa".

    School.district imeandikwa kwa njia tofauti tofauti ("Kyerwa" vs
    "Kyerwa Dc"). TC/MC HAZIondolewi — "Tarime Tc" na "Tarime Dc" ni
    halmashauri mbili tofauti.
    """
    key = re.sub(r'\s+', ' ', (name or '').strip().lower())
    key = re.sub(r'\s+(dc|d\.c\.?|district council|district)$', '', key)
    return key


def schools_in_district(district, region=''):
    """Shule zote za district hii (bila kujali 'Dc' / herufi kubwa)."""
    from .models import School

    key = district_key(district)
    if not key:
        return School.objects.none()
    qs = School.objects.filter(district__istartswith=key.split(' ')[0])
    if region:
        qs = qs.filter(region__iexact=region.strip())
    ids = [s.pk for s in qs if district_key(s.district) == key]
    return School.objects.filter(pk__in=ids)


def district_program_name(school):
    """Jina la wilaya kama shule hii inaweza kujiunga na joint ya wilaya
    (wilaya ina Afisa Wilaya au joint exam), vinginevyo None."""
    from .models import TeacherAccount

    if school is None or not school.district:
        return None
    key = district_key(school.district)
    first = key.split(' ')[0]
    for d in list(JointExam.objects.filter(district__istartswith=first)
                  .values_list('district', flat=True).distinct()) + list(
        TeacherAccount.objects.filter(role=TeacherAccount.ROLE_DISTRICT, district__istartswith=first)
        .values_list('district', flat=True).distinct()
    ):
        if district_key(d) == key:
            return d
    return None


def joints_for_school(school):
    key = district_key(school.district)
    return [j for j in JointExam.objects.filter(district__istartswith=key.split(' ')[0])
            if district_key(j.district) == key]


def is_empty_placeholder(school):
    """Shule isiyo na chochote kinachoitegemea (akaunti, mitihani, wanafunzi,
    masomo...) — rekodi iliyoundwa kutoka orodha ya Halmashauri ambayo
    hakuna aliyeitumia bado. Inakagua KILA uhusiano kupitia Collector ya
    Django, si orodha tunayoikumbuka."""
    from django.db.models.deletion import Collector

    collector = Collector(using=school._state.db or 'default')
    collector.collect([school])
    related = sum(len(objs) for objs in collector.data.values()) - 1
    related += sum(qs.count() for qs in collector.fast_deletes)
    # on_delete=SET_NULL (mf. TeacherAccount.school, Exam.school) haziingii
    # kwenye data — Collector inaziweka kwenye field_updates
    for objs in collector.field_updates.values():
        for obj in objs:
            related += obj.count() if hasattr(obj, 'count') and not isinstance(obj, models.Model) else 1
    return related == 0


class JointExam(models.Model):
    """Mtihani mmoja wa pamoja wa wilaya — unaunganisha Exam za shule zote."""

    name = models.CharField(max_length=150, help_text='Mf: FORM ONE MID TERM JOINT EXAMINATION')
    exam_type = models.CharField(max_length=20, default='DISTRICT_JOINT')
    year = models.PositiveIntegerField()
    form = models.PositiveIntegerField()
    date = models.DateField(null=True, blank=True)
    district = models.CharField(max_length=100)
    region = models.CharField(max_length=100, blank=True, default='')
    subjects = models.ManyToManyField(
        'Subject', blank=True, related_name='joint_exams',
        help_text='Masomo ya mtihani huu (kila shule inapata yale inayofundisha).',
    )
    # Shule zinaona ranking ya wilaya tu baada ya afisa kuifungua — ili
    # matokeo ya nusu (shule nyingine bado hazijamaliza) yasionekane.
    published = models.BooleanField(
        default=False,
        help_text='Shule zote za wilaya zinaona performance ya shule zote.',
    )
    created_by = models.ForeignKey(
        'TeacherAccount', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_joint_exams',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-year', '-created_at']
        verbose_name = 'Joint exam (wilaya)'
        verbose_name_plural = 'Joint exams (wilaya)'

    def __str__(self):
        return f'{self.name} — Form {self.form} {self.year} ({self.district})'

    def attach_school(self, school):
        """Unda (au pata) Exam ya shule hii kwa joint hii + SubjectSubmission
        za masomo ambayo shule inafundisha kwa form hii. Shule ambayo haijaweka
        masomo yake (SchoolSubject) inapata masomo yote ya joint."""
        from .models import Exam, SchoolSubject, SubjectSubmission

        exam = Exam.objects.filter(joint_exam=self, school=school).first()
        if exam is None:
            exam = Exam.objects.create(
                name=self.name, year=self.year, form=self.form,
                exam_type=self.exam_type, date=self.date,
                school=school, school_name=school.name, joint_exam=self,
            )

        joint_subjects = list(self.subjects.all())
        offered = {
            ss.subject_id
            for ss in SchoolSubject.objects.filter(school=school)
            if str(self.form) in [f.strip() for f in (ss.form_levels or '').split(',')]
        }
        for subject in joint_subjects:
            if offered and subject.pk not in offered:
                continue
            SubjectSubmission.objects.get_or_create(exam=exam, subject=subject)
        return exam
