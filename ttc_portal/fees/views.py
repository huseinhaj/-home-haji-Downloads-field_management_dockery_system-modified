import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import FeeBill, FeeItem, Payment
from .services import generate_control_number, control_number_is_valid, refresh_bill_status
from .forms import FeeItemForm, PaymentSubmissionForm
from . import gepg

logger = logging.getLogger(__name__)


# ───────────────────────────── Student actions ─────────────────────────────

def _get_own_bill(user, bill_id):
    student = getattr(user, 'student_profile', None)
    if student is None:
        return None, None
    bill = get_object_or_404(FeeBill, id=bill_id, student=student)
    return student, bill


@login_required
def generate_control(request, bill_id):
    """SR2 flow: student generates a unique control number for an unpaid bill."""
    student, bill = _get_own_bill(request.user, bill_id)
    if student is None:
        messages.error(request, 'Akaunti yako si ya mwanafunzi.')
        return redirect('home')

    if bill.is_fully_paid:
        messages.warning(request, 'Bili hii tayari imelipwa kikamilifu.')
        return redirect('dashboard')

    if bill.control_number and control_number_is_valid(bill):
        messages.info(request, 'Ukweli: una namba ya malipo inayofanya kazi tayari.')
    else:
        control_number = generate_control_number(bill)
        if control_number:
            messages.success(
                request,
                f"Namba yako ya malipo imezalishwa: {control_number}",
            )
        else:
            messages.error(request, 'Imeshindikana kuzalisha namba ya malipo. Jaribu tena.')
    return redirect('dashboard')


@login_required
def submit_payment(request, bill_id):
    """Student reports a payment made against a control number (awaiting confirmation)."""
    student, bill = _get_own_bill(request.user, bill_id)
    if student is None:
        messages.error(request, 'Akaunti yako si ya mwanafunzi.')
        return redirect('home')

    if request.method == 'POST':
        form = PaymentSubmissionForm(request.POST)
        if form.is_valid():
            if not control_number_is_valid(bill):
                messages.warning(
                    request,
                    'Huna namba ya malipo inayofanya kazi. Tafadhali generate kwanza.',
                )
                return redirect('dashboard')

            amount = form.cleaned_data['amount']
            if amount > bill.remaining_amount:
                messages.warning(
                    request,
                    f"Kiasi ulichoweka (TZS {amount:,.0f}) kinazidi deni la bili hii "
                    f"(TZS {bill.remaining_amount:,.0f}).",
                )
                return redirect('dashboard')

            Payment.objects.create(
                bill=bill,
                student=student,
                amount=amount,
                method=form.cleaned_data['method'],
                reference=form.cleaned_data['reference'],
                notes=form.cleaned_data['notes'],
                status='pending',
            )
            messages.success(
                request,
                'Malipo yako yamepokelewa na yanasubiri kuthibitishwa na msimamizi wa chuo chako.',
            )
            return redirect('dashboard')
        messages.error(request, 'Tafadhali sahihisha makosa kwenye fomu.')
    return redirect('dashboard')


# ───────────────────────────── GePG webhook (malipo otomatiki) ─────────────────────────────

@csrf_exempt
def gepg_notification(request):
    """Webhook ya GePG — malipo yanathibitishwa MOJA KWA MOJA.

    GePG inatuma taarifa ya malipo hapa (XML au JSON kwa sandbox testing)
    baada ya mwanafunzi kulipa kwa control number. Ikiwa
    TTC_GEPG_NOTIFICATION_TOKEN imewekwa, ombi lazima liwe na header
    `X-GEPG-Token` (au `?token=`) inayolingana.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    token = getattr(settings, 'TTC_GEPG_NOTIFICATION_TOKEN', '')
    supplied = request.headers.get('X-GEPG-Token') or request.GET.get('token', '')
    if token and supplied != token:
        return HttpResponse(
            '<Gepg><gepgPaymentAck><StsCode>7202</StsCode>'
            '<Desc>Invalid token</Desc></gepgPaymentAck></Gepg>',
            content_type='application/xml', status=401,
        )

    try:
        bill, payment, created = gepg.handle_payment_notification(request.body)
    except Exception:
        logger.exception('GePG notification processing error')
        return HttpResponse(
            '<Gepg><gepgPaymentAck><StsCode>7201</StsCode>'
            '<Desc>Processing error</Desc></gepgPaymentAck></Gepg>',
            content_type='application/xml', status=500,
        )

    if bill is None:
        return HttpResponse(
            '<Gepg><gepgPaymentAck><StsCode>7201</StsCode>'
            '<Desc>Control number not found</Desc></gepgPaymentAck></Gepg>',
            content_type='application/xml', status=404,
        )

    if created:
        logger.info('GePG webhook: malipo mapya yamethibitishwa (payment=%s)', payment.pk)
    return HttpResponse(
        '<Gepg><gepgPaymentAck><StsCode>7101</StsCode>'
        '<Desc>SUCCESSFUL</Desc></gepgPaymentAck></Gepg>',
        content_type='application/xml',
    )


# ───────────────────────────── College admin: fees & payments ─────────────────────────────

def _get_admin_college(user):
    profile = getattr(user, 'college_admin_profile', None)
    return profile.college if profile else None


@login_required
def admin_fees(request):
    college = _get_admin_college(request.user)
    if college is None:
        messages.error(request, 'Huna ruhusa ya kufikia ukurasa huu.')
        return redirect('home')
    fee_items = FeeItem.objects.filter(college=college)
    context = {'college': college, 'fee_items': fee_items}
    return render(request, 'fees/admin_fees.html', context)


@login_required
def admin_fee_add(request):
    college = _get_admin_college(request.user)
    if college is None:
        messages.error(request, 'Huna ruhusa ya kufikia ukurasa huu.')
        return redirect('home')
    if request.method == 'POST':
        form = FeeItemForm(request.POST)
        if form.is_valid():
            fee_item = form.save(commit=False)
            fee_item.college = college
            fee_item.save()
            messages.success(
                request,
                f'"{fee_item.name}" (TZS {fee_item.amount:,.0f}) imeongezwa. '
                'Wanafunzi wapya watapewa bili yake moja kwa moja.',
            )
            return redirect('admin_fees')
    else:
        form = FeeItemForm()
    return render(request, 'fees/admin_fee_add.html', {'form': form, 'college': college})


@login_required
def admin_fee_toggle(request, fee_id):
    college = _get_admin_college(request.user)
    if college is None:
        return redirect('home')
    fee_item = get_object_or_404(FeeItem, id=fee_id, college=college)
    fee_item.is_active = not fee_item.is_active
    fee_item.save(update_fields=['is_active'])
    state = 'imewashwa' if fee_item.is_active else 'imezimwa'
    messages.success(request, f'"{fee_item.name}" {state}.')
    return redirect('admin_fees')


@login_required
def admin_payments(request):
    college = _get_admin_college(request.user)
    if college is None:
        messages.error(request, 'Huna ruhusa ya kufikia ukurasa huu.')
        return redirect('home')

    status_filter = request.GET.get('status', 'pending')
    payments = Payment.objects.filter(bill__student__college=college).select_related(
        'bill__fee_item', 'student'
    )
    if status_filter in ('pending', 'confirmed', 'rejected'):
        payments = payments.filter(status=status_filter)
    context = {
        'college': college,
        'payments': payments.order_by('-created_at'),
        'status_filter': status_filter,
    }
    return render(request, 'fees/admin_payments.html', context)


@login_required
def admin_payment_confirm(request, payment_id, action):
    """Reconcile a payment: confirm it against the bill and refresh status."""
    college = _get_admin_college(request.user)
    if college is None:
        return redirect('home')
    payment = get_object_or_404(
        Payment, id=payment_id, bill__student__college=college
    )
    if action == 'confirm':
        if payment.status == 'pending':
            payment.status = 'confirmed'
            payment.confirmed_by = request.user
            payment.confirmed_at = timezone.now()
            payment.save()
            refresh_bill_status(payment.bill)
            messages.success(
                request,
                f'Malipo ya TZS {payment.amount:,.0f} ya {payment.student.full_name} '
                'yamethibitishwa.',
            )
    elif action == 'reject':
        if payment.status == 'pending':
            payment.status = 'rejected'
            payment.notes = (payment.notes or '') + ' [Ilikataliwa]'
            payment.save()
            messages.warning(request, 'Malipo yamekataliwa.')
    return redirect('admin_payments')
