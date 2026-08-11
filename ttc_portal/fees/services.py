"""fees/services.py — SR2-style business logic.

- Derives the current academic year (August–July cycle, like Tanzania schools).
- Auto-creates a bill (bili) for every active fee item when a student registers.
- Generates unique GePG-style control numbers (namba ya malipo) on demand.
"""

import random
from datetime import timedelta

from django.utils import timezone
from django.conf import settings

from .models import FeeItem, FeeBill


def academic_year_now():
    """Academic year in Tanzania runs Aug–Jul. 11 Aug 2026 → '2026/2027'."""
    today = timezone.now().date()
    if today.month >= 8:
        return f"{today.year}/{today.year + 1}"
    return f"{today.year - 1}/{today.year}"


def create_bills_for_student(student, academic_year=None):
    """Create bills for all active fee items of the student's college.

    SR2 flow: every student automatically gets a bill per fee item; the
    control number is only generated when the student clicks 'Generate'.
    """
    academic_year = academic_year or academic_year_now()
    created = 0
    for fee_item in FeeItem.objects.filter(college=student.college, is_active=True):
        if fee_item.year_of_study and fee_item.year_of_study != student.year_of_study:
            continue
        bill, was_created = FeeBill.objects.get_or_create(
            student=student,
            fee_item=fee_item,
            academic_year=academic_year,
            defaults={'amount': fee_item.amount},
        )
        if was_created:
            created += 1
    return created


def generate_control_number(bill):
    """Generate a unique GePG-style control number (10 digits starting with 99).

    Numbers are unique across the whole system and expire after
    TTC_CONTROL_NUMBER_LIFETIME_DAYS days (SR2/GePG behaviour).
    """
    prefix = settings.TTC_CONTROL_NUMBER_PREFIX
    digits_needed = max(1, 10 - len(prefix))
    for _ in range(100):
        candidate = prefix + ''.join(str(random.randint(0, 9)) for _ in range(digits_needed))
        if not FeeBill.objects.filter(control_number=candidate).exclude(pk=bill.pk).exists():
            bill.control_number = candidate
            bill.control_number_generated_at = timezone.now()
            bill.control_number_expires = timezone.now() + timedelta(
                days=settings.TTC_CONTROL_NUMBER_LIFETIME_DAYS
            )
            bill.save(update_fields=[
                'control_number', 'control_number_generated_at', 'control_number_expires',
            ])
            return candidate
    return None


def control_number_is_valid(bill):
    if not bill.control_number:
        return False
    if bill.control_number_expires and bill.control_number_expires < timezone.now():
        return False
    return True


def refresh_bill_status(bill):
    """Recompute bill status from confirmed payments (paid/partial/unpaid)."""
    paid = sum(
        p.amount for p in bill.payments.filter(status='confirmed')
    )
    if paid >= bill.amount:
        bill.status = 'paid'
    elif paid > 0:
        bill.status = 'partially_paid'
    else:
        bill.status = 'unpaid'
    bill.save(update_fields=['status'])
    return bill.status
